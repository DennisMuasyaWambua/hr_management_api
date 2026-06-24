import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0005_candidate_crm_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='TalentPool',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('criteria', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.UUIDField(blank=True, null=True)),
            ],
            options={'db_table': 'talent_pools'},
        ),
        migrations.CreateModel(
            name='TalentPoolMember',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pool', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='recruitment.talentpool')),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pool_memberships', to='recruitment.candidate')),
                ('added_by', models.UUIDField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'talent_pool_members'},
        ),
        migrations.AddConstraint(
            model_name='talentpoolmember',
            constraint=models.UniqueConstraint(fields=['pool', 'candidate'], name='unique_pool_candidate'),
        ),
        migrations.CreateModel(
            name='CandidateTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(default='#6B7280', max_length=20)),
            ],
            options={'db_table': 'candidate_tags'},
        ),
        migrations.AddConstraint(
            model_name='candidatetag',
            constraint=models.UniqueConstraint(fields=['company_id', 'name'], name='unique_company_tag_name'),
        ),
        migrations.CreateModel(
            name='CandidateTagAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='recruitment.candidatetag')),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tag_assignments', to='recruitment.candidate')),
            ],
            options={'db_table': 'candidate_tag_assignments'},
        ),
        migrations.AddConstraint(
            model_name='candidatetagassignment',
            constraint=models.UniqueConstraint(fields=['tag', 'candidate'], name='unique_tag_candidate'),
        ),
        migrations.CreateModel(
            name='CandidateNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crm_notes', to='recruitment.candidate')),
                ('note_type', models.CharField(
                    choices=[('call', 'Call'), ('email', 'Email'), ('meeting', 'Meeting'),
                             ('note', 'Note'), ('linkedin', 'LinkedIn')],
                    default='note', max_length=20,
                )),
                ('body', models.TextField()),
                ('author_id', models.UUIDField(blank=True, null=True)),
                ('author_name', models.CharField(blank=True, default='', max_length=200)),
            ],
            options={'db_table': 'candidate_notes', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CandidateActivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='recruitment.candidate')),
                ('event_type', models.CharField(
                    choices=[
                        ('applied', 'Applied'), ('stage_changed', 'Stage changed'),
                        ('note_added', 'Note added'), ('tag_added', 'Tag added'),
                        ('tag_removed', 'Tag removed'), ('pool_added', 'Pool added'),
                        ('pool_removed', 'Pool removed'), ('interview_scheduled', 'Interview scheduled'),
                        ('interview_completed', 'Interview completed'), ('offer_sent', 'Offer sent'),
                        ('hired', 'Hired'), ('rejected', 'Rejected'),
                        ('converted', 'Converted'), ('referral_submitted', 'Referral submitted'),
                    ],
                    max_length=50,
                )),
                ('description', models.TextField(blank=True, default='')),
                ('actor_id', models.UUIDField(blank=True, null=True)),
                ('actor_name', models.CharField(blank=True, default='', max_length=200)),
                ('metadata', models.JSONField(blank=True, default=dict)),
            ],
            options={'db_table': 'candidate_activities', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='candidateactivity',
            index=models.Index(fields=['company_id', 'candidate_id'], name='candidateact_company_cand_idx'),
        ),
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referrals', to='recruitment.candidate')),
                ('referrer_employee_id', models.UUIDField(blank=True, null=True)),
                ('referrer_name', models.CharField(max_length=200)),
                ('referrer_email', models.EmailField()),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('hired', 'Hired'),
                             ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn')],
                    default='pending', max_length=20,
                )),
                ('notes', models.TextField(blank=True, default='')),
                ('bonus_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('bonus_paid_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'referrals'},
        ),
        migrations.CreateModel(
            name='CandidateScoreBreakdown',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('candidate', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='score_breakdown', to='recruitment.candidate')),
                ('skill_score', models.FloatField(blank=True, null=True)),
                ('experience_score', models.FloatField(blank=True, null=True)),
                ('industry_score', models.FloatField(blank=True, null=True)),
                ('location_score', models.FloatField(blank=True, null=True)),
                ('total_score', models.FloatField(blank=True, null=True)),
                ('scoring_notes', models.TextField(blank=True, default='')),
                ('scored_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'candidate_score_breakdowns'},
        ),
    ]
