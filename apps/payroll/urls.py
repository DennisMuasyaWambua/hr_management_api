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

from .views_approvals import (ApproverConfigViewSet, DocuSealWebhook,
                              PayrollApprovalViewSet, PayrollDocumentViewSet,
                              PayrollWorkflowView, ShareView)

router = DefaultRouter()
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')
router.register('employees', EmployeePaymentViewSet, basename='employee-payment')
router.register('employee-payroll-status', EmployeePayrollStatusViewSet, basename='employee-payroll-status')
router.register('payment-history', PaymentHistoryViewSet, basename='payment-history')
router.register('pesapal', PesaPalConfigViewSet, basename='pesapal-config')
router.register('intasend', IntaSendConfigViewSet, basename='intasend-config')

# Approval workflow (additive — nothing above changes)
router.register('approver-config', ApproverConfigViewSet, basename='approver-config')
router.register('payroll-approvals', PayrollApprovalViewSet, basename='payroll-approvals')
router.register('payroll-documents', PayrollDocumentViewSet, basename='payroll-documents')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/pesapal/ipn/', PesaPalIPNWebhook.as_view(), name='pesapal-ipn'),
    path('api/payroll-workflow/<uuid:run_id>/<str:verb>/',
         PayrollWorkflowView.as_view(), name='payroll-workflow'),
    path('api/docuseal/webhook/', DocuSealWebhook.as_view(), name='docuseal-webhook'),
    path('api/share/', ShareView.as_view(), name='share'),
]
