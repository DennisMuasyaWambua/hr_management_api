from rest_framework import serializers

from .models import (AllowanceType, ComplianceAlert, DeductionType,
                     DisciplinaryRecord, EmployeeAllowance, EmployeeCertificate,
                     EmployeeDeduction, EmployeeExit, ExitClearanceItem,
                     LeaveRecall, MinimumWage, OvertimeRequest, Reimbursement,
                     StatutoryRate)


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
