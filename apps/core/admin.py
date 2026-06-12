from django.contrib import admin

from .models import (NotificationLog, NotificationTemplate, OneTapToken,
                     Permission, Role, RolePermission, ServiceAuditLog,
                     UserRoleAssignment)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'rank', 'company_id', 'is_system')
    list_filter = ('is_system',)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('codename', 'module')
    list_filter = ('module',)


admin.site.register(RolePermission)
admin.site.register(UserRoleAssignment)
admin.site.register(NotificationTemplate)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'channel', 'recipient', 'event', 'status', 'attempts')
    list_filter = ('channel', 'status')


@admin.register(ServiceAuditLog)
class ServiceAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor_user_id', 'object_type', 'object_id')
    list_filter = ('action',)


admin.site.register(OneTapToken)
