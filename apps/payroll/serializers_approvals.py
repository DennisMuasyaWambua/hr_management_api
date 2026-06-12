from rest_framework import serializers

from .approval_models import (ApproverConfig, PayrollApproval, PayrollApprover,
                              PayrollDocument)


class PayrollApproverSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollApprover
        fields = ['id', 'user_id', 'name', 'email', 'phone', 'order', 'is_active']


class ApproverConfigSerializer(serializers.ModelSerializer):
    approvers = PayrollApproverSerializer(many=True)

    class Meta:
        model = ApproverConfig
        fields = ['id', 'company_id', 'tenant_id', 'required_approvals',
                  'is_active', 'approvers', 'created_at', 'updated_at']

    def create(self, validated_data):
        approvers = validated_data.pop('approvers', [])
        config = ApproverConfig.objects.create(**validated_data)
        for a in approvers:
            PayrollApprover.objects.create(config=config, **a)
        return config

    def update(self, instance, validated_data):
        approvers = validated_data.pop('approvers', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if approvers is not None:
            instance.approvers.all().delete()
            for a in approvers:
                PayrollApprover.objects.create(config=instance, **a)
        return instance


class PayrollApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollApproval
        fields = '__all__'


class ShareRequestSerializer(serializers.Serializer):
    """Body for the share-to-email endpoint."""
    module = serializers.ChoiceField(choices=['payroll'], default='payroll')
    object_id = serializers.UUIDField(help_text='Payroll run id')
    format = serializers.ChoiceField(choices=['pdf', 'excel'], default='pdf')
    recipients = serializers.ListField(child=serializers.EmailField())
    message = serializers.CharField(required=False, allow_blank=True)
    document_title = serializers.CharField(required=False, allow_blank=True)


class PayrollDocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PayrollDocument
        fields = ['id', 'payroll_run_id', 'payroll_record_id', 'doc_type',
                  'sha256', 'password_protected', 'is_signed', 'is_locked',
                  'docuseal_submission_id', 'generated_by', 'created_at',
                  'download_url']

    def get_download_url(self, obj):
        return f'/api/payroll-documents/{obj.id}/download/'
