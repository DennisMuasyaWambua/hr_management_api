from django.contrib import admin
from .models import Company, EmployeeProfile, PayrollRun, PayrollRecord, PaymentBatch


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant_id', 'contact_email', 'is_active', 'created_at']
    search_fields = ['name', 'contact_email']
    list_filter = ['is_active', 'created_at']


@admin.register(EmployeeProfile)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'employee_number', 'job_title', 'company', 'salary',
        'payment_method', 'employment_status'
    ]
    search_fields = ['employee_number', 'job_title']
    list_filter = ['employment_status', 'payment_method', 'company']


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = [
        'period_display', 'period_month', 'period_year',
        'company', 'status', 'total_net'
    ]
    search_fields = ['company__name']
    list_filter = ['status', 'company', 'period_year']

    def period_display(self, obj):
        return obj.period_display
    period_display.short_description = 'Period'


@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'payroll_run', 'gross_salary',
        'net_salary', 'payment_status'
    ]
    search_fields = ['employee__employee_number']
    list_filter = ['payment_status', 'payment_method']


@admin.register(PaymentBatch)
class PaymentBatchAdmin(admin.ModelAdmin):
    list_display = [
        'payroll_run', 'payment_method', 'status',
        'total_amount', 'record_count'
    ]
    list_filter = ['status', 'payment_method']
