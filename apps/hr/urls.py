from rest_framework.routers import DefaultRouter

from .views import (AllowanceTypeViewSet, ComplianceAlertViewSet,
                    DeductionTypeViewSet, DisciplinaryRecordViewSet,
                    EmployeeAllowanceViewSet, EmployeeCertificateViewSet,
                    EmployeeDeductionViewSet, EmployeeExitViewSet,
                    LeaveRecallViewSet, MinimumWageViewSet,
                    OvertimeRequestViewSet, ReimbursementViewSet,
                    StatutoryRateViewSet)

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
router.register('leave-recalls', LeaveRecallViewSet, basename='leave-recalls')
router.register('certificates', EmployeeCertificateViewSet, basename='certificates')

urlpatterns = router.urls
