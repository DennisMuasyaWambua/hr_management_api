from rest_framework import serializers

from .models import (
    CandidateActivity, CandidateNote, CandidateScoreBreakdown,
    CandidateTag, CandidateTagAssignment, Referral,
    TalentPool, TalentPoolMember,
)


class TalentPoolSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = TalentPool
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']

    def get_member_count(self, obj):
        return obj.members.count()


class TalentPoolMemberSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)

    class Meta:
        model = TalentPoolMember
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class CandidateTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateTag
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class CandidateTagAssignmentSerializer(serializers.ModelSerializer):
    tag_name = serializers.CharField(source='tag.name', read_only=True)
    tag_color = serializers.CharField(source='tag.color', read_only=True)

    class Meta:
        model = CandidateTagAssignment
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class CandidateNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateNote
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class CandidateActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateActivity
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ReferralSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)

    class Meta:
        model = Referral
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class CandidateScoreBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateScoreBreakdown
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
