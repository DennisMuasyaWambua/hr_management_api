import uuid

from django.db import models

from apps.hr.models import TenantStamped


class RecruitmentClient(TenantStamped):
    STATUSES = [
        ('prospect', 'Prospect'), ('active', 'Active'),
        ('inactive', 'Inactive'), ('churned', 'Churned'),
    ]

    name = models.CharField(max_length=200)
    industry = models.CharField(max_length=100, null=True, blank=True)
    website = models.CharField(max_length=300, null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    account_manager_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='active')
    notes = models.TextField(blank=True, default='')
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'crm_clients'
        ordering = ['name']

    def __str__(self):
        return self.name


class ClientContact(TenantStamped):
    client = models.ForeignKey(RecruitmentClient, on_delete=models.CASCADE,
                               related_name='contacts')
    full_name = models.CharField(max_length=200)
    job_title = models.CharField(max_length=200, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    linkedin_url = models.CharField(max_length=500, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    is_hiring_manager = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'crm_client_contacts'

    def __str__(self):
        return f'{self.full_name} @ {self.client_id}'


class ClientContract(TenantStamped):
    CONTRACT_TYPES = [
        ('retained', 'Retained'), ('contingency', 'Contingency'),
        ('exclusive', 'Exclusive'), ('msa', 'Master Service Agreement'),
    ]
    STATUSES = [
        ('draft', 'Draft'), ('active', 'Active'),
        ('expired', 'Expired'), ('terminated', 'Terminated'),
    ]

    client = models.ForeignKey(RecruitmentClient, on_delete=models.CASCADE,
                               related_name='contracts')
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPES,
                                     default='contingency')
    title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='KES')
    fee_percentage = models.DecimalField(max_digits=5, decimal_places=2,
                                         null=True, blank=True)
    replacement_days = models.PositiveIntegerField(default=90)
    status = models.CharField(max_length=20, choices=STATUSES, default='draft')
    document_url = models.CharField(max_length=500, null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'crm_contracts'

    def __str__(self):
        return self.title


class ClientSLA(TenantStamped):
    contract = models.ForeignKey(ClientContract, on_delete=models.CASCADE,
                                  related_name='slas')
    metric = models.CharField(max_length=100)
    target_days = models.PositiveIntegerField()
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'crm_slas'

    def __str__(self):
        return f'{self.metric} ({self.target_days}d)'


class ClientMeetingNote(TenantStamped):
    MEETING_TYPES = [
        ('call', 'Call'), ('meeting', 'Meeting'),
        ('email', 'Email'), ('site_visit', 'Site Visit'),
    ]

    client = models.ForeignKey(RecruitmentClient, on_delete=models.CASCADE,
                               related_name='meeting_notes')
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES, default='call')
    meeting_date = models.DateField()
    attendees = models.JSONField(default=list, blank=True)
    summary = models.TextField()
    action_items = models.JSONField(default=list, blank=True)
    author_id = models.UUIDField(null=True, blank=True)
    author_name = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        db_table = 'crm_meeting_notes'
        ordering = ['-meeting_date']

    def __str__(self):
        return f'{self.meeting_type} with {self.client_id} on {self.meeting_date}'


class Placement(TenantStamped):
    STATUSES = [
        ('offered', 'Offered'), ('accepted', 'Accepted'),
        ('started', 'Started'), ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    client = models.ForeignKey(RecruitmentClient, on_delete=models.CASCADE,
                               related_name='placements')
    candidate = models.ForeignKey('recruitment.Candidate', on_delete=models.CASCADE,
                                  related_name='placements')
    job_posting = models.ForeignKey('recruitment.JobPosting', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='placements')
    contact = models.ForeignKey(ClientContact, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='placements')
    contract = models.ForeignKey(ClientContract, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='placements')
    job_title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='KES')
    placement_fee = models.DecimalField(max_digits=14, decimal_places=2,
                                        null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='offered')
    replacement_deadline = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'crm_placements'

    def __str__(self):
        return f'{self.candidate_id} → {self.client_id}'
