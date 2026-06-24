import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('recruitment', '0006_crm_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobMatchScore',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('candidate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='match_scores', to='recruitment.candidate',
                )),
                ('job_posting', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='match_scores', to='recruitment.jobposting',
                )),
                ('provider', models.CharField(default='rule_based', max_length=50)),
                ('skill_score', models.FloatField(blank=True, null=True)),
                ('experience_score', models.FloatField(blank=True, null=True)),
                ('education_score', models.FloatField(blank=True, null=True)),
                ('location_score', models.FloatField(blank=True, null=True)),
                ('total_score', models.FloatField(blank=True, null=True)),
                ('scoring_notes', models.TextField(blank=True, default='')),
                ('scored_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'job_match_scores'},
        ),
        migrations.AddConstraint(
            model_name='jobmatchscore',
            constraint=models.UniqueConstraint(
                fields=['candidate', 'job_posting'],
                name='unique_candidate_job_score',
            ),
        ),
        migrations.AddIndex(
            model_name='jobmatchscore',
            index=models.Index(
                fields=['company_id', 'job_posting_id', 'total_score'],
                name='jms_company_job_score_idx',
            ),
        ),
    ]
