from django.contrib import admin

from .models import (
    Organization, Permission, Role, RolePermission, UserRole, OrganigramNode,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'status', 'industry', 'country')
    list_filter = ('type', 'status')
    search_fields = ('name',)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('resource', 'action', 'description')
    list_filter = ('resource',)
    search_fields = ('resource', 'action')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_system_role')
    list_filter = ('is_system_role',)
    search_fields = ('name',)


admin.site.register(RolePermission)
admin.site.register(UserRole)
admin.site.register(OrganigramNode)
