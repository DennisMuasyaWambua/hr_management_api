from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import ServiceAuditLog
from apps.core.permissions import request_company_id, request_user_id
from apps.hr.views import CompanyScopedViewSet

from .models import (
    ClientContact, ClientContract, ClientMeetingNote,
    ClientSLA, Placement, RecruitmentClient,
)
from .serializers import (
    ClientContactSerializer, ClientContractSerializer,
    ClientMeetingNoteSerializer, ClientSLASerializer,
    PlacementSerializer, RecruitmentClientSerializer,
)


class RecruitmentClientViewSet(CompanyScopedViewSet):
    queryset = RecruitmentClient.objects.filter(is_deleted=False)
    serializer_class = RecruitmentClientSerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        account_manager_id = self.request.query_params.get('account_manager_id')
        if account_manager_id:
            qs = qs.filter(account_manager_id=account_manager_id)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(email__icontains=q) |
                Q(industry__icontains=q)
            )
        return qs

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        ServiceAuditLog.log('crm.client_deleted', request=self.request,
                            object_type='RecruitmentClient', object_id=str(instance.id),
                            company_id=instance.company_id)

    @action(detail=True, methods=['get'])
    def contacts(self, request, pk=None):
        client = self.get_object()
        qs = ClientContact.objects.filter(client=client)
        return Response({'count': qs.count(),
                         'results': ClientContactSerializer(qs, many=True).data})

    @action(detail=True, methods=['get'])
    def contracts(self, request, pk=None):
        client = self.get_object()
        qs = ClientContract.objects.filter(client=client)
        return Response({'count': qs.count(),
                         'results': ClientContractSerializer(qs, many=True).data})

    @action(detail=True, methods=['get'])
    def placements(self, request, pk=None):
        client = self.get_object()
        qs = Placement.objects.select_related('candidate').filter(client=client)
        return Response({'count': qs.count(),
                         'results': PlacementSerializer(qs, many=True).data})

    @action(detail=True, methods=['get'], url_path='meeting-notes')
    def meeting_notes(self, request, pk=None):
        client = self.get_object()
        qs = ClientMeetingNote.objects.filter(client=client)
        return Response({'count': qs.count(),
                         'results': ClientMeetingNoteSerializer(qs, many=True).data})


class ClientContactViewSet(CompanyScopedViewSet):
    queryset = ClientContact.objects.select_related('client').all()
    serializer_class = ClientContactSerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)
        is_hm = self.request.query_params.get('is_hiring_manager')
        if is_hm in ('true', 'false'):
            qs = qs.filter(is_hiring_manager=(is_hm == 'true'))
        return qs


class ClientContractViewSet(CompanyScopedViewSet):
    queryset = ClientContract.objects.select_related('client').prefetch_related('slas').all()
    serializer_class = ClientContractSerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    @action(detail=True, methods=['get'])
    def slas(self, request, pk=None):
        contract = self.get_object()
        qs = ClientSLA.objects.filter(contract=contract)
        return Response({'count': qs.count(),
                         'results': ClientSLASerializer(qs, many=True).data})


class ClientSLAViewSet(CompanyScopedViewSet):
    queryset = ClientSLA.objects.select_related('contract').all()
    serializer_class = ClientSLASerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        contract_id = self.request.query_params.get('contract_id')
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        return qs


class ClientMeetingNoteViewSet(CompanyScopedViewSet):
    queryset = ClientMeetingNote.objects.select_related('client').all()
    serializer_class = ClientMeetingNoteSerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        actor_id = request_user_id(self.request)
        serializer.save(company_id=company_id, author_id=actor_id)


class PlacementViewSet(CompanyScopedViewSet):
    queryset = Placement.objects.select_related('client', 'candidate').all()
    serializer_class = PlacementSerializer
    rbac_module = 'crm'

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        return qs
