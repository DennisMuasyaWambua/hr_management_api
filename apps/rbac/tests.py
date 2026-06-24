"""
Part B3 — tenant isolation + RBAC enforcement tests.

Covers the spec's required assertions:
  * a user from Organization A cannot read/resolve Organization B's grants
  * a recruiter cannot access payroll endpoints
  * a finance_approver cannot access candidate CVs
  * a candidate cannot create vacancies
plus smoke coverage of the B2 company-admin endpoints (auto-provisioning,
per-company role scoping, permission matrix, assign/revoke).
"""
import uuid

from django.test import TestCase, RequestFactory, override_settings
from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.rbac.models import (
    Organization, Permission, Role, RolePermission, UserRole,
)
from apps.rbac.permissions import resolve_permissions, HasRBACPermission


class SeededRoleDefaultsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_orgrbac')

    def _codes(self, role_name):
        role = Role.objects.get(name=role_name, organization=None)
        return {rp.permission.code for rp in
                role.role_permissions.select_related('permission')}

    def test_recruiter_cannot_access_payroll(self):
        self.assertFalse(any(c.startswith('payroll.') for c in self._codes('recruiter')))

    def test_finance_approver_cannot_access_candidates(self):
        self.assertFalse(any(c.startswith('candidate.') for c in self._codes('finance_approver')))

    def test_candidate_cannot_create_vacancies(self):
        self.assertNotIn('vacancy.create', self._codes('candidate'))

    def test_super_admin_has_every_permission(self):
        self.assertEqual(len(self._codes('super_admin')), Permission.objects.count())


class CrossTenantResolveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_orgrbac')
        cls.org_a = Organization.objects.create(name='Org A', type='CLIENT')
        cls.org_b = Organization.objects.create(name='Org B', type='CLIENT')
        payroll_view = Permission.objects.get(resource='payroll', action='view')
        role_a = Role.objects.create(name='A-Payroll', organization=cls.org_a)
        RolePermission.objects.create(role=role_a, permission=payroll_view)
        cls.user = uuid.uuid4()
        UserRole.objects.create(user_id=cls.user, role=role_a, organization=cls.org_a)

    def test_permission_resolves_in_own_org(self):
        self.assertIn('payroll.view', resolve_permissions(self.user, self.org_a))

    def test_no_permission_leaks_to_other_org(self):
        self.assertEqual(resolve_permissions(self.user, self.org_b), set())

    def test_unrelated_user_has_no_permissions(self):
        self.assertEqual(resolve_permissions(uuid.uuid4(), self.org_a), set())


@override_settings(RBAC_ENFORCE=True)
class PermissionEnforcementTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_orgrbac')
        cls.org = Organization.objects.create(name='Org C', type='CLIENT')
        perm = Permission.objects.get(resource='payroll', action='approve')
        role = Role.objects.create(name='C-Finance', organization=cls.org)
        RolePermission.objects.create(role=role, permission=perm)
        cls.allowed_user = uuid.uuid4()
        UserRole.objects.create(user_id=cls.allowed_user, role=role, organization=cls.org)
        cls.denied_user = uuid.uuid4()

    def _request(self, user_id):
        factory = RequestFactory()
        return factory.get(
            '/x',
            HTTP_X_USER_ID=str(user_id),
            HTTP_X_ORGANIZATION_ID=str(self.org.id),
        )

    class _View:
        action = 'create'
        required_permissions = {'create': 'payroll.approve'}

    def test_user_with_permission_is_allowed(self):
        self.assertTrue(
            HasRBACPermission().has_permission(self._request(self.allowed_user), self._View()))

    def test_user_without_permission_is_denied(self):
        self.assertFalse(
            HasRBACPermission().has_permission(self._request(self.denied_user), self._View()))


def _rows(data):
    """Normalize a DRF list response (paginated dict or plain list)."""
    if isinstance(data, dict):
        return data.get('results', [])
    return list(data)


class CompanyAdminEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_orgrbac')

    def _create_company(self, name):
        res = self.client.post('/api/orgrbac/organizations/',
                               {'name': name, 'type': 'CLIENT'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['id']

    def test_create_company_autoprovisions_client_admin(self):
        org_id = self._create_company('EABL')
        self.assertTrue(
            Role.objects.filter(name='client_admin', organization_id=org_id).exists())

    def test_seed_roles_then_set_matrix(self):
        org_id = self._create_company('Airtel')
        seeded = self.client.post(f'/api/orgrbac/organizations/{org_id}/seed-roles/')
        self.assertEqual(seeded.status_code, 200, seeded.content)
        roles = self.client.get(f'/api/orgrbac/roles/?organization={org_id}')
        names = {r['name'] for r in _rows(roles.data)}
        self.assertIn('hiring_manager', names)

        role = Role.objects.get(name='hiring_manager', organization_id=org_id)
        put = self.client.put(
            f'/api/orgrbac/roles/{role.id}/permissions/',
            {'permissions': ['payroll.view', 'payroll.approve']}, format='json')
        self.assertEqual(put.status_code, 200, put.content)
        self.assertEqual(set(put.data['permissions']), {'payroll.view', 'payroll.approve'})

    def test_roles_are_scoped_per_company(self):
        a = self._create_company('CompA')
        b = self._create_company('CompB')
        ra = self.client.get(f'/api/orgrbac/roles/?organization={a}')
        rows = _rows(ra.data)
        a_ids = {str(r['id']) for r in rows}
        b_ids = {str(i) for i in
                 Role.objects.filter(organization_id=b).values_list('id', flat=True)}
        # The A query must not leak any of B's roles.
        self.assertTrue(a_ids.isdisjoint(b_ids))
        # And every role returned for A must actually belong to A.
        for r in rows:
            self.assertEqual(str(r['organization']), str(a))

    def test_assign_and_revoke_role(self):
        org_id = self._create_company('CompZ')
        role = Role.objects.get(name='client_admin', organization_id=org_id)
        uid = str(uuid.uuid4())
        assigned = self.client.post('/api/orgrbac/user-roles/',
                                    {'user_id': uid, 'role': str(role.id),
                                     'organization': org_id}, format='json')
        self.assertEqual(assigned.status_code, 201, assigned.content)
        ur_id = assigned.data['id']
        revoked = self.client.delete(f'/api/orgrbac/user-roles/{ur_id}/')
        self.assertIn(revoked.status_code, (200, 204))
        self.assertFalse(UserRole.objects.filter(id=ur_id).exists())

    def test_me_endpoint_returns_permissions(self):
        org_id = self._create_company('CompMe')
        role = Role.objects.get(name='client_admin', organization_id=org_id)
        uid = str(uuid.uuid4())
        self.client.post('/api/orgrbac/user-roles/',
                         {'user_id': uid, 'role': str(role.id),
                          'organization': org_id}, format='json')
        org = Organization.objects.get(id=org_id)
        res = self.client.get('/api/orgrbac/me/',
                              HTTP_X_USER_ID=uid,
                              HTTP_X_ORGANIZATION_ID=str(org.id))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('organization.manage', res.data['permissions'])
