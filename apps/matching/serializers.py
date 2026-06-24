from rest_framework import serializers

from .models import JobMatchScore


class JobMatchScoreSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)
    job_posting_title = serializers.CharField(source='job_posting.title', read_only=True)

    class Meta:
        model = JobMatchScore
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'scored_at']


class RankedCandidateSerializer(serializers.ModelSerializer):
    candidate_id = serializers.UUIDField(source='candidate.id', read_only=True)
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)
    current_stage = serializers.CharField(source='candidate.current_stage', read_only=True)

    class Meta:
        model = JobMatchScore
        fields = [
            'id', 'candidate_id', 'candidate_name', 'candidate_email',
            'current_stage', 'provider',
            'skill_score', 'experience_score', 'education_score',
            'location_score', 'total_score', 'scoring_notes', 'scored_at',
        ]
