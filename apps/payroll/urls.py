from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PayrollRunViewSet,
    EmployeePaymentViewSet,
    PesaPalConfigViewSet,
    PesaPalIPNWebhook
)

router = DefaultRouter()
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')
router.register('employees', EmployeePaymentViewSet, basename='employee-payment')
router.register('pesapal', PesaPalConfigViewSet, basename='pesapal-config')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/pesapal/ipn/', PesaPalIPNWebhook.as_view(), name='pesapal-ipn'),
]
