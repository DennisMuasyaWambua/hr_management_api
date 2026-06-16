from rest_framework import serializers

from .models import (AllowanceType, Announcement, BackgroundCheck,
                     ComplianceAlert, DeductionType, DisciplinaryRecord,
                     EmployeeAllowance, EmployeeCertificate,
                     EmployeeDeduction, EmployeeExit,
                     EmployeeOnboardingDocument, ExitClearanceItem,
                     KpiAssignment, LeaveBalance, LeaveRecall, LeaveRequest,
                     MedicalRecord, MinimumWage, OvertimeRequest,
                     PerformanceReview, Reimbursement, StatutoryRate,
                     TrainingEnrollment, TrainingSession)


class AllowanceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowanceType
        fields = '__all__'


class EmployeeAllowanceSerializer(serializers.ModelSerializer):
    allowance_name = serializers.CharField(source='allowance_type.name', read_only=True)
    is_variable = serializers.BooleanField(source='allowance_type.is_variable',
                                           read_only=True)

    class Meta:
        model = EmployeeAllowance
        fields = '__all__'


class DeductionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeductionType
        fields = '__all__'


class EmployeeDeductionSerializer(serializers.ModelSerializer):
    deduction_name = serializers.CharField(source='deduction_type.name', read_only=True)

    class Meta:
        model = EmployeeDeduction
        fields = '__all__'


class OvertimeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = OvertimeRequest
        fields = '__all__'
        read_only_fields = ['status', 'decided_by', 'decided_at']


class ReimbursementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reimbursement
        fields = '__all__'
        read_only_fields = ['processed_by', 'processed_at', 'payment_reference']


class StatutoryRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutoryRate
        fields = '__all__'


class MinimumWageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MinimumWage
        fields = '__all__'


class ComplianceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceAlert
        fields = '__all__'


class DisciplinaryRecordSerializer(serializers.ModelSerializer):
    escalations = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = DisciplinaryRecord
        fields = '__all__'


class ExitClearanceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExitClearanceItem
        fields = '__all__'


class EmployeeExitSerializer(serializers.ModelSerializer):
    clearance_items = ExitClearanceItemSerializer(many=True, read_only=True)

    class Meta:
        model = EmployeeExit
        fields = '__all__'


class LeaveRecallSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRecall
        fields = '__all__'
        read_only_fields = ['status', 'decided_by', 'decided_at']


class EmployeeCertificateSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmployeeCertificate
        fields = '__all__'


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = '__all__'
        read_only_fields = ['status', 'approved_by', 'approved_at', 'rejection_reason']


class LeaveBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveBalance
        fields = '__all__'


class AnnouncementSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Announcement
        fields = '__all__'


class MedicalRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecord
        fields = '__all__'


class BackgroundCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackgroundCheck
        fields = '__all__'
        read_only_fields = ['requested_at']


class KpiAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KpiAssignment
        fields = '__all__'


class PerformanceReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceReview
        fields = '__all__'


class TrainingSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingSession
        fields = '__all__'


class TrainingEnrollmentSerializer(serializers.ModelSerializer):
    """Nests the session fields the dashboard's TabTraining expects
    (title/trainer_name/start_date/.../is_mandatory) alongside attendance."""
    title = serializers.CharField(source='session.title', read_only=True)
    description = serializers.CharField(source='session.description', read_only=True)
    trainer_name = serializers.CharField(source='session.trainer_name', read_only=True)
    start_date = serializers.DateField(source='session.start_date', read_only=True)
    end_date = serializers.DateField(source='session.end_date', read_only=True)
    is_mandatory = serializers.BooleanField(source='session.is_mandatory', read_only=True)
    department = serializers.CharField(source='session.department', read_only=True)

    class Meta:
        model = TrainingEnrollment
        fields = ['id', 'session', 'employee_id', 'attendance_status', 'score',
                  'certificate_url', 'title', 'description', 'trainer_name',
                  'start_date', 'end_date', 'is_mandatory', 'department',
                  'created_at', 'updated_at']


class EmployeeOnboardingDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeOnboardingDocument
        fields = '__all__'
