from django.db import models
from django.utils import timezone


class ActionRecord(models.Model):
    """
    Thin overlay tracking user interactions with generated actions.

    PK format: "{source_module}:{source_record_id}:{action_type}"
    Only written on first user interaction (dismiss/escalate).
    Source models remain authoritative — this table stores no business data.
    """
    id = models.CharField(max_length=200, primary_key=True)
    company_id = models.UUIDField(db_index=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.UUIDField(null=True, blank=True)
    dismiss_reason = models.TextField(default='', blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalated_by = models.UUIDField(null=True, blank=True)
    escalate_note = models.TextField(default='', blank=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'action_records'

    def __str__(self):
        return self.id
