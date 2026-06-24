import uuid

from django.db import models


class JobMatchScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company_id = models.UUIDField(db_index=True)
    candidate = models.ForeignKey(
        'recruitment.Candidate', on_delete=models.CASCADE,
        related_name='match_scores',
    )
    job_posting = models.ForeignKey(
        'recruitment.JobPosting', on_delete=models.CASCADE,
        related_name='match_scores',
    )
    provider = models.CharField(max_length=50, default='rule_based')
    skill_score = models.FloatField(null=True, blank=True)
    experience_score = models.FloatField(null=True, blank=True)
    education_score = models.FloatField(null=True, blank=True)
    location_score = models.FloatField(null=True, blank=True)
    total_score = models.FloatField(null=True, blank=True)
    scoring_notes = models.TextField(blank=True, default='')
    scored_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'job_match_scores'
        unique_together = [('candidate', 'job_posting')]
        indexes = [
            models.Index(
                fields=['company_id', 'job_posting_id', 'total_score'],
                name='jms_company_job_score_idx',
            ),
        ]

    def __str__(self):
        return f'{self.candidate_id} vs {self.job_posting_id}: {self.total_score}'
