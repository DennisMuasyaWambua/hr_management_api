"""
Recruitment models (Django-managed, replaces direct-Supabase tables used by
the careers Next.js app): job postings, candidates, job alerts.

db_table names match the original Supabase schema 1:1 (see
HR-SYSTEM/packages/shared/src/supabase/database.types.ts) so this is a
drop-in replacement, not a new shape.
"""
import uuid

from django.db import models

from apps.hr.models import TenantStamped


class JobPosting(TenantStamped):
    EMPLOYMENT_TYPES = [('white_collar', 'White collar'), ('casual', 'Casual')]
    STATUSES = [('open', 'Open'), ('closed', 'Closed'), ('on_hold', 'On hold')]

    is_deleted = models.BooleanField(default=False)
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=120, null=True, blank=True)
    description = models.TextField()
    required_keywords = models.JSONField(default=list, blank=True)
    nice_to_have_keywords = models.JSONField(default=list, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES,
                                       default='white_collar')
    status = models.CharField(max_length=20, choices=STATUSES, default='open')
    auto_reject_threshold = models.IntegerField(default=0)
    closing_date = models.DateField(null=True, blank=True)
    created_by = models.UUIDField(null=True, blank=True)
    location_name = models.CharField(max_length=200, null=True, blank=True)
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    experience_level = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'job_postings'

    def __str__(self):
        return self.title


class Candidate(TenantStamped):
    STAGES = [
        ('screened', 'Screened'), ('interview_l1', 'Interview L1'),
        ('interview_l2', 'Interview L2'), ('offer_sent', 'Offer sent'),
        ('hired', 'Hired'), ('rejected', 'Rejected'),
    ]

    is_deleted = models.BooleanField(default=False)
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE,
                                    related_name='candidates',
                                    db_column='job_posting_id')
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=30, null=True, blank=True)
    cv_url = models.CharField(max_length=500, default='', blank=True)
    cv_text = models.TextField(null=True, blank=True)
    ai_score = models.FloatField(null=True, blank=True)
    ai_summary = models.TextField(null=True, blank=True)
    ai_extracted_skills = models.JSONField(default=list, blank=True)
    ai_experience_years = models.FloatField(null=True, blank=True)
    ai_education = models.CharField(max_length=200, null=True, blank=True)
    current_stage = models.CharField(max_length=20, choices=STAGES, default='screened')
    rejection_reason = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    tracking_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    data_consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    data_retention_months = models.IntegerField(null=True, blank=True)
    source = models.CharField(max_length=50, default='careers_site')

    class Meta:
        db_table = 'candidates'

    def __str__(self):
        return f'{self.full_name} -> {self.job_posting_id}'


class JobAlert(TenantStamped):
    FREQUENCIES = [('instant', 'Instant'), ('daily', 'Daily'), ('weekly', 'Weekly')]

    name = models.CharField(max_length=120, null=True, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, null=True, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    categories = models.JSONField(default=list, blank=True)
    job_types = models.JSONField(default=list, blank=True)
    experience_levels = models.JSONField(default=list, blank=True)
    location_name = models.CharField(max_length=200, null=True, blank=True)
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    radius_km = models.IntegerField(default=50)
    frequency = models.CharField(max_length=20, choices=FREQUENCIES, default='instant')
    is_active = models.BooleanField(default=True)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        db_table = 'job_alerts'

    def __str__(self):
        return self.email


class JobAlertLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.ForeignKey(JobAlert, on_delete=models.CASCADE,
                              related_name='logs', db_column='alert_id')
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE,
                                    db_column='job_posting_id')
    channel = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default='sent')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'job_alert_logs'
