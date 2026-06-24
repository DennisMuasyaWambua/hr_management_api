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
            name='RecruitmentClient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('name', models.CharField(max_length=200)),
                ('industry', models.CharField(blank=True, max_length=100, null=True)),
                ('website', models.CharField(blank=True, max_length=300, null=True)),
                ('location', models.CharField(blank=True, max_length=200, null=True)),
                ('phone', models.CharField(blank=True, max_length=30, null=True)),
                ('email', models.EmailField(blank=True, null=True)),
                ('account_manager_id', models.UUIDField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('prospect', 'Prospect'), ('active', 'Active'),
                             ('inactive', 'Inactive'), ('churned', 'Churned')],
                    default='active', max_length=20,
                )),
                ('notes', models.TextField(blank=True, default='')),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'crm_clients', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ClientContact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contacts', to='crm.recruitmentclient',
                )),
                ('full_name', models.CharField(max_length=200)),
                ('job_title', models.CharField(blank=True, max_length=200, null=True)),
                ('email', models.EmailField(blank=True, null=True)),
                ('phone', models.CharField(blank=True, max_length=30, null=True)),
                ('linkedin_url', models.CharField(blank=True, max_length=500, null=True)),
                ('is_primary', models.BooleanField(default=False)),
                ('is_hiring_manager', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'crm_client_contacts'},
        ),
        migrations.CreateModel(
            name='ClientContract',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contracts', to='crm.recruitmentclient',
                )),
                ('contract_type', models.CharField(
                    choices=[('retained', 'Retained'), ('contingency', 'Contingency'),
                             ('exclusive', 'Exclusive'), ('msa', 'Master Service Agreement')],
                    default='contingency', max_length=20,
                )),
                ('title', models.CharField(max_length=200)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('value', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('currency', models.CharField(default='KES', max_length=3)),
                ('fee_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('replacement_days', models.PositiveIntegerField(default=90)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('active', 'Active'),
                             ('expired', 'Expired'), ('terminated', 'Terminated')],
                    default='draft', max_length=20,
                )),
                ('document_url', models.CharField(blank=True, max_length=500, null=True)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'crm_contracts'},
        ),
        migrations.CreateModel(
            name='ClientSLA',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='slas', to='crm.clientcontract',
                )),
                ('metric', models.CharField(max_length=100)),
                ('target_days', models.PositiveIntegerField()),
                ('description', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'crm_slas'},
        ),
        migrations.CreateModel(
            name='ClientMeetingNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='meeting_notes', to='crm.recruitmentclient',
                )),
                ('meeting_type', models.CharField(
                    choices=[('call', 'Call'), ('meeting', 'Meeting'),
                             ('email', 'Email'), ('site_visit', 'Site Visit')],
                    default='call', max_length=20,
                )),
                ('meeting_date', models.DateField()),
                ('attendees', models.JSONField(blank=True, default=list)),
                ('summary', models.TextField()),
                ('action_items', models.JSONField(blank=True, default=list)),
                ('author_id', models.UUIDField(blank=True, null=True)),
                ('author_name', models.CharField(blank=True, default='', max_length=200)),
            ],
            options={'db_table': 'crm_meeting_notes', 'ordering': ['-meeting_date']},
        ),
        migrations.CreateModel(
            name='Placement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='placements', to='crm.recruitmentclient',
                )),
                ('candidate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='placements', to='recruitment.candidate',
                )),
                ('job_posting', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='placements', to='recruitment.jobposting',
                )),
                ('contact', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='placements', to='crm.clientcontact',
                )),
                ('contract', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='placements', to='crm.clientcontract',
                )),
                ('job_title', models.CharField(max_length=200)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('salary', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('currency', models.CharField(default='KES', max_length=3)),
                ('placement_fee', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('status', models.CharField(
                    choices=[('offered', 'Offered'), ('accepted', 'Accepted'),
                             ('started', 'Started'), ('completed', 'Completed'),
                             ('cancelled', 'Cancelled')],
                    default='offered', max_length=20,
                )),
                ('replacement_deadline', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'crm_placements'},
        ),
    ]
