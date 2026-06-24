from rest_framework import serializers

from .models import (
    Organization, Permission, Role, RolePermission, UserRole, OrganigramNode,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'type', 'status', 'industry', 'country',
            'logo_url', 'company_id', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PermissionSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'resource', 'action', 'code', 'description']


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'name', 'description', 'organization', 'is_system_role',
            'permission_codes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_system_role', 'created_at', 'updated_at']

    def get_permission_codes(self, obj):
        return [rp.permission.code for rp in obj.role_permissions.select_related('permission')]


class UserRoleSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)

    class Meta:
        model = UserRole
        fields = ['id', 'user_id', 'role', 'role_name', 'organization', 'created_at']
        read_only_fields = ['id', 'created_at']


class OrganigramNodeSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True, default=None)

    class Meta:
        model = OrganigramNode
        fields = [
            'id', 'organization', 'role', 'role_name', 'parent_node',
            'title', 'user_id', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
