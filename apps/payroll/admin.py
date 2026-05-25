from django.contrib import admin
from .models import Company, Employee, PayrollRun, PayrollRecord, PaymentBatch


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant_id', 'created_at']
    search_fields = ['name']
    list_filter = ['created_at']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'user', 'company', 'salary', 'payment_method', 'status']
    search_fields = ['employee_number', 'user__email', 'user__first_name', 'user__last_name']
    list_filter = ['status', 'payment_method', 'company']


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ['period_start', 'period_end', 'company', 'status', 'employee_count', 'total_net']
    search_fields = ['company__name']
    list_filter = ['status', 'company']
    date_hierarchy = 'period_start'


@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'payroll_run', 'gross_pay', 'net_pay', 'payment_status']
    search_fields = ['employee__employee_number']
    list_filter = ['payment_status', 'payment_method']


@admin.register(PaymentBatch)
class PaymentBatchAdmin(admin.ModelAdmin):
    list_display = ['payroll_run', 'payment_method', 'status', 'total_amount', 'record_count']
    list_filter = ['status', 'payment_method']
