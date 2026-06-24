from django.contrib import admin

from .models import ActionRecord


@admin.register(ActionRecord)
class ActionRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'company_id', 'first_seen_at', 'dismissed_at', 'escalated_at']
    list_filter = ['dismissed_at', 'escalated_at']
    search_fields = ['id']
    readonly_fields = ['id', 'company_id', 'first_seen_at', 'updated_at']
