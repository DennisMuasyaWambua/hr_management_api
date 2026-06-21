from rest_framework import serializers

from .models import (AppUser, NotificationLog, NotificationTemplate,
                     Permission, Role, RolePermission, ServiceAuditLog,
                     StaffAssignment, UserRoleAssignment)


class AppUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppUser
        fields = ['id', 'full_name', 'email', 'role', 'avatar_url', 'phone',
                  'is_active', 'preferred_language', 'last_login_at',
                  'company_id', 'employee_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'email', 'employee_id', 'created_at', 'updated_at']


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'codename', 'module', 'description']


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ['id', 'company_id', 'tenant_id', 'slug', 'name', 'rank',
                  'is_system', 'permissions', 'created_at', 'updated_at']

    def get_permissions(self, obj):
        return [g.permission.codename for g in
                obj.grants.select_related('permission').all()]


class RolePermissionSerializer(serializers.ModelSerializer):
    codename = serializers.CharField(source='permission.codename', read_only=True)

    class Meta:
        model = RolePermission
        fields = ['id', 'role', 'permission', 'codename', 'granted_by', 'created_at']


class UserRoleAssignmentSerializer(serializers.ModelSerializer):
    role_slug = serializers.CharField(source='role.slug', read_only=True)

    class Meta:
        model = UserRoleAssignment
        fields = ['id', 'user_id', 'company_id', 'tenant_id', 'role',
                  'role_slug', 'assigned_by', 'created_at']


class StaffAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffAssignment
        fields = ['id', 'company_id', 'tenant_id', 'staff_user_id',
                  'employee_id', 'assigned_by', 'created_at']
        read_only_fields = ['id', 'assigned_by', 'created_at']


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = '__all__'


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = '__all__'
        read_only_fields = [f.name for f in NotificationLog._meta.fields]


class ServiceAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceAuditLog
        fields = '__all__'


class SendNotificationSerializer(serializers.Serializer):
    """Direct send API used by all three frontends."""
    event = serializers.CharField(required=False, allow_blank=True, default='')
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=['email', 'sms', 'whatsapp']),
        default=['email'])
    recipients = serializers.ListField(child=serializers.DictField())
    context = serializers.DictField(required=False, default=dict)
    subject = serializers.CharField(required=False, allow_blank=True, default='')
    message = serializers.CharField(required=False, allow_blank=True, default='')
    company_id = serializers.UUIDField(required=False, allow_null=True)
    source_app = serializers.ChoiceField(
        choices=['careers', 'dashboard', 'pwa', 'system'], default='dashboard')
