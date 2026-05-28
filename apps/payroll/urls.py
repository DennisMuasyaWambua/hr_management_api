from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PayrollRunViewSet,
    EmployeePaymentViewSet,
    EmployeePayrollStatusViewSet,
    PaymentHistoryViewSet,
    PesaPalConfigViewSet,
    PesaPalIPNWebhook,
    IntaSendConfigViewSet
)

router = DefaultRouter()
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')
router.register('employees', EmployeePaymentViewSet, basename='employee-payment')
router.register('employee-payroll-status', EmployeePayrollStatusViewSet, basename='employee-payroll-status')
router.register('payment-history', PaymentHistoryViewSet, basename='payment-history')
router.register('pesapal', PesaPalConfigViewSet, basename='pesapal-config')
router.register('intasend', IntaSendConfigViewSet, basename='intasend-config')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/pesapal/ipn/', PesaPalIPNWebhook.as_view(), name='pesapal-ipn'),
]
