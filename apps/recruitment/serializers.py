from rest_framework import serializers

from .models import Candidate, Interview, JobAlert, JobAlertLog, JobPosting


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


class InterviewSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    job_posting_title = serializers.CharField(source='job_posting.title', read_only=True)
    feedback_score = serializers.IntegerField(
        min_value=1, max_value=10, required=False, allow_null=True,
    )

    class Meta:
        model = Interview
        fields = '__all__'
        read_only_fields = ['completed_at', 'cancelled_at']


class ConvertCandidateSerializer(serializers.Serializer):
    """Payload required to convert a hired candidate into an EmployeeProfile."""
    job_title = serializers.CharField(max_length=255)
    department = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    employment_type = serializers.ChoiceField(
        choices=['full_time', 'part_time', 'contract', 'intern'], default='full_time'
    )
    worker_class = serializers.ChoiceField(
        choices=['white_collar', 'blue_collar'], default='white_collar'
    )
    salary = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=['bank', 'mpesa', 'airtel'])
    start_date = serializers.DateField()
    employee_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
