import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Interview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('interview_type', models.CharField(
                    choices=[('l1', 'Level 1'), ('l2', 'Level 2'),
                             ('technical', 'Technical'), ('hr', 'HR'), ('final', 'Final')],
                    default='l1', max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('scheduled', 'Scheduled'), ('completed', 'Completed'),
                             ('cancelled', 'Cancelled'), ('no_show', 'No Show')],
                    default='scheduled', max_length=20,
                )),
                ('scheduled_at', models.DateTimeField()),
                ('location', models.CharField(blank=True, default='', max_length=255)),
                ('interviewer_ids', models.JSONField(blank=True, default=list)),
                ('notes', models.TextField(blank=True, default='')),
                ('feedback_score', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('feedback_notes', models.TextField(blank=True, default='')),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_reason', models.TextField(blank=True, default='')),
                ('created_by', models.UUIDField(blank=True, null=True)),
                ('candidate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='interviews',
                    to='recruitment.candidate',
                )),
                ('job_posting', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='interviews',
                    to='recruitment.jobposting',
                )),
            ],
            options={
                'db_table': 'interviews',
                'ordering': ['scheduled_at'],
            },
        ),
    ]
