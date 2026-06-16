from rest_framework import serializers

from .models import Candidate, JobAlert, JobAlertLog, JobPosting


class JobPostingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosting
        fields = '__all__'


class JobPostingPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosting
        fields = ['id', 'title', 'department', 'description', 'required_keywords',
                  'nice_to_have_keywords', 'employment_type', 'closing_date',
                  'created_at', 'location_name', 'location_lat', 'location_lng',
                  'experience_level']


class CandidateSerializer(serializers.ModelSerializer):
    """Admin (dashboard) serializer — nests a job_posting summary, matching
    the CandidateWithPosting shape the dashboard's hooks already expect."""
    job_posting = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = '__all__'

    def get_job_posting(self, obj):
        jp = obj.job_posting
        return {'title': jp.title, 'department': jp.department, 'company_id': jp.company_id}


class CandidateTrackSerializer(serializers.ModelSerializer):
    job_posting = JobPostingPublicSerializer(read_only=True)

    class Meta:
        model = Candidate
        fields = ['id', 'full_name', 'email', 'phone', 'current_stage',
                  'created_at', 'job_posting']


class JobAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAlert
        fields = '__all__'
        read_only_fields = ['unsubscribe_token', 'is_active']


class JobAlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAlertLog
        fields = '__all__'
