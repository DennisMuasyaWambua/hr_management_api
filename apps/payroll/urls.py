from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PayrollRunViewSet,
    EmployeePaymentViewSet,
    EmployeePayrollStatusViewSet,
    PaymentHistoryViewSet,
    PesaPalConfigViewSet,
    PesaPalIPNWebhook,
    IntaSendConfigViewSet,
    AuthLoginView,
    MeView,
    CompanyViewSet,
    EmployeeProfileViewSet,
    MyPayslipsView,
    ProfilePictureView,
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
router.register('companies', CompanyViewSet, basename='company')
router.register('all-employees', EmployeeProfileViewSet, basename='all-employees')

# Approval workflow (additive — nothing above changes)
router.register('approver-config', ApproverConfigViewSet, basename='approver-config')
router.register('payroll-approvals', PayrollApprovalViewSet, basename='payroll-approvals')
router.register('payroll-documents', PayrollDocumentViewSet, basename='payroll-documents')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/auth/login/', AuthLoginView.as_view(), name='auth-login'),
    path('api/me/', MeView.as_view(), name='me'),
    path('api/me/payslips/', MyPayslipsView.as_view(), name='my-payslips'),
    path('api/me/profile-picture/', ProfilePictureView.as_view(), name='me-profile-picture'),
    path('api/pesapal/ipn/', PesaPalIPNWebhook.as_view(), name='pesapal-ipn'),
    path('api/payroll-workflow/<uuid:run_id>/<str:verb>/',
         PayrollWorkflowView.as_view(), name='payroll-workflow'),
    path('api/docuseal/webhook/', DocuSealWebhook.as_view(), name='docuseal-webhook'),
    path('api/share/', ShareView.as_view(), name='share'),
]
