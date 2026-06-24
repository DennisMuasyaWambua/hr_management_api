from django.urls import path
from rest_framework.routers import DefaultRouter

from .analytics import WorkforceAnalyticsView
from .dashboard import DashboardSummaryView
from .views import (AllowanceTypeViewSet, AnnouncementViewSet,
                    BackgroundCheckViewSet, ComplianceAlertViewSet,
                    DeductionTypeViewSet, DisciplinaryRecordViewSet,
                    EmployeeAllowanceViewSet, EmployeeCertificateViewSet,
                    EmployeeDeductionViewSet, EmployeeExitViewSet,
                    ExitClearanceViewSet,
                    EmployeeOnboardingDocumentViewSet, KpiAssignmentViewSet,
                    LeaveBalanceViewSet, LeaveRecallViewSet,
                    LeaveRequestViewSet, MedicalRecordViewSet,
                    MinimumWageViewSet, OnboardingSummaryView,
                    OvertimeRequestViewSet, PerformanceReviewViewSet,
                    ReimbursementViewSet, StatutoryRateViewSet,
                    TrainingEnrollmentViewSet, TrainingSessionViewSet)

router = DefaultRouter()
router.register('allowance-types', AllowanceTypeViewSet, basename='allowance-types')
router.register('allowances', EmployeeAllowanceViewSet, basename='allowances')
router.register('deduction-types', DeductionTypeViewSet, basename='deduction-types')
router.register('deductions', EmployeeDeductionViewSet, basename='deductions')
router.register('overtime', OvertimeRequestViewSet, basename='overtime')
router.register('reimbursements', ReimbursementViewSet, basename='reimbursements')
router.register('statutory-rates', StatutoryRateViewSet, basename='statutory-rates')
router.register('minimum-wages', MinimumWageViewSet, basename='minimum-wages')
router.register('compliance-alerts', ComplianceAlertViewSet, basename='compliance-alerts')
router.register('disciplinary', DisciplinaryRecordViewSet, basename='disciplinary')
router.register('exits', EmployeeExitViewSet, basename='exits')
router.register('exit-clearances', ExitClearanceViewSet, basename='exit-clearances')
router.register('leave-recalls', LeaveRecallViewSet, basename='leave-recalls')
router.register('certificates', EmployeeCertificateViewSet, basename='certificates')
router.register('leave', LeaveRequestViewSet, basename='leave')
router.register('leave-balances', LeaveBalanceViewSet, basename='leave-balances')
router.register('announcements', AnnouncementViewSet, basename='announcements')
router.register('medical-records', MedicalRecordViewSet, basename='medical-records')
router.register('background-checks', BackgroundCheckViewSet, basename='background-checks')
router.register('kpi-assignments', KpiAssignmentViewSet, basename='kpi-assignments')
router.register('performance-reviews', PerformanceReviewViewSet, basename='performance-reviews')
router.register('training-sessions', TrainingSessionViewSet, basename='training-sessions')
router.register('training-enrollments', TrainingEnrollmentViewSet, basename='training-enrollments')
router.register('onboarding-documents', EmployeeOnboardingDocumentViewSet, basename='onboarding-documents')

urlpatterns = router.urls + [
    # ── Dashboard & Analytics (read-only aggregates) ───────────────────────
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('analytics/workforce/', WorkforceAnalyticsView.as_view(), name='analytics-workforce'),
    # ── Existing paths ─────────────────────────────────────────────────────
    path('onboarding/summary/', OnboardingSummaryView.as_view(), name='onboarding-summary'),
    path('exits/<uuid:exit_pk>/clearance/', ExitClearanceViewSet.as_view({
        'get': 'list', 'post': 'create',
    }), name='exit-clearance-list'),
    path('exits/<uuid:exit_pk>/clearance/<uuid:pk>/', ExitClearanceViewSet.as_view({
        'get': 'retrieve', 'patch': 'partial_update', 'put': 'update',
    }), name='exit-clearance-detail'),
    path('exits/<uuid:exit_pk>/clearance/<uuid:pk>/sign_section/', ExitClearanceViewSet.as_view({
        'post': 'sign_section',
    }), name='exit-clearance-sign'),
]
