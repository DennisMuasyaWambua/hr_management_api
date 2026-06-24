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
    EDUCATION_LEVELS = [
        ('high_school', 'High School'), ('bachelors', 'Bachelors'),
        ('masters', 'Masters'), ('phd', 'PhD'), ('other', 'Other'),
    ]

    # Conversion tracking — set atomically when convert() succeeds
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_employee_id = models.UUIDField(null=True, blank=True)
    recruiter_id = models.UUIDField(null=True, blank=True, db_index=True)
    # CRM extensions (Phase 2)
    is_passive = models.BooleanField(default=False)
    availability_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)
    experience_years = models.PositiveIntegerField(null=True, blank=True)
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVELS,
                                       null=True, blank=True)
    linkedin_url = models.CharField(max_length=500, null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)

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


class Interview(TenantStamped):
    """
    Backing record for a scheduled interview against a candidate.

    Created automatically when CandidateViewSet.stage() advances a candidate
    to interview_l1 or interview_l2, or created explicitly via the
    InterviewViewSet. Decoupled from stage so HR can schedule independently.
    """
    TYPES = [
        ('l1', 'Level 1'), ('l2', 'Level 2'),
        ('technical', 'Technical'), ('hr', 'HR'), ('final', 'Final'),
    ]
    STATUSES = [
        ('scheduled', 'Scheduled'), ('completed', 'Completed'),
        ('cancelled', 'Cancelled'), ('no_show', 'No Show'),
    ]

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name='interviews',
    )
    job_posting = models.ForeignKey(
        JobPosting, on_delete=models.CASCADE, related_name='interviews',
    )
    interview_type = models.CharField(max_length=20, choices=TYPES, default='l1')
    status = models.CharField(max_length=20, choices=STATUSES, default='scheduled')
    scheduled_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True, default='')
    # UUIDs of AppUser records who will conduct the interview
    interviewer_ids = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default='')
    # Feedback submitted after the interview
    feedback_score = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_notes = models.TextField(blank=True, default='')
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.TextField(blank=True, default='')
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'interviews'
        ordering = ['scheduled_at']

    def __str__(self):
        return f'{self.candidate.full_name} — {self.interview_type} @ {self.scheduled_at}'


class TalentPool(TenantStamped):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    criteria = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'talent_pools'

    def __str__(self):
        return self.name


class TalentPoolMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    pool = models.ForeignKey(TalentPool, on_delete=models.CASCADE,
                             related_name='members')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE,
                                  related_name='pool_memberships')
    added_by = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'talent_pool_members'
        unique_together = [('pool', 'candidate')]


class CandidateTag(TenantStamped):
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default='#6B7280')

    class Meta:
        db_table = 'candidate_tags'
        unique_together = [('company_id', 'name')]

    def __str__(self):
        return self.name


class CandidateTagAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    tag = models.ForeignKey(CandidateTag, on_delete=models.CASCADE,
                            related_name='assignments')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE,
                                  related_name='tag_assignments')

    class Meta:
        db_table = 'candidate_tag_assignments'
        unique_together = [('tag', 'candidate')]


class CandidateNote(TenantStamped):
    NOTE_TYPES = [
        ('call', 'Call'), ('email', 'Email'), ('meeting', 'Meeting'),
        ('note', 'Note'), ('linkedin', 'LinkedIn'),
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE,
                                  related_name='crm_notes')
    note_type = models.CharField(max_length=20, choices=NOTE_TYPES, default='note')
    body = models.TextField()
    author_id = models.UUIDField(null=True, blank=True)
    author_name = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        db_table = 'candidate_notes'
        ordering = ['-created_at']


class CandidateActivity(models.Model):
    EVENT_TYPES = [
        ('applied', 'Applied'), ('stage_changed', 'Stage changed'),
        ('note_added', 'Note added'), ('tag_added', 'Tag added'),
        ('tag_removed', 'Tag removed'), ('pool_added', 'Pool added'),
        ('pool_removed', 'Pool removed'), ('interview_scheduled', 'Interview scheduled'),
        ('interview_completed', 'Interview completed'), ('offer_sent', 'Offer sent'),
        ('hired', 'Hired'), ('rejected', 'Rejected'),
        ('converted', 'Converted'), ('referral_submitted', 'Referral submitted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    company_id = models.UUIDField(db_index=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE,
                                  related_name='activities')
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    description = models.TextField(blank=True, default='')
    actor_id = models.UUIDField(null=True, blank=True)
    actor_name = models.CharField(max_length=200, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'candidate_activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'candidate_id']),
        ]


class Referral(TenantStamped):
    STATUSES = [
        ('pending', 'Pending'), ('hired', 'Hired'),
        ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn'),
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE,
                                  related_name='referrals')
    referrer_employee_id = models.UUIDField(null=True, blank=True)
    referrer_name = models.CharField(max_length=200)
    referrer_email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUSES, default='pending')
    notes = models.TextField(blank=True, default='')
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2,
                                       null=True, blank=True)
    bonus_paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'referrals'


class CandidateScoreBreakdown(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company_id = models.UUIDField(db_index=True)
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE,
                                     related_name='score_breakdown')
    skill_score = models.FloatField(null=True, blank=True)
    experience_score = models.FloatField(null=True, blank=True)
    industry_score = models.FloatField(null=True, blank=True)
    location_score = models.FloatField(null=True, blank=True)
    total_score = models.FloatField(null=True, blank=True)
    scoring_notes = models.TextField(blank=True, default='')
    scored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'candidate_score_breakdowns'


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
