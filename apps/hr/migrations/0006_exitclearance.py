import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0005_backgroundcheck_validation_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExitClearance',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('exit', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='clearance', to='hr.employeeexit')),
                ('initiated_by', models.UUIDField(blank=True, null=True)),
                # IT section
                ('it_cleared', models.BooleanField(default=False)),
                ('it_cleared_by', models.CharField(blank=True, default='', max_length=200)),
                ('it_cleared_at', models.DateTimeField(blank=True, null=True)),
                ('it_notes', models.TextField(blank=True, default='')),
                # Finance section
                ('finance_cleared', models.BooleanField(default=False)),
                ('finance_cleared_by', models.CharField(blank=True, default='', max_length=200)),
                ('finance_cleared_at', models.DateTimeField(blank=True, null=True)),
                ('finance_notes', models.TextField(blank=True, default='')),
                # Admin section
                ('admin_cleared', models.BooleanField(default=False)),
                ('admin_cleared_by', models.CharField(blank=True, default='', max_length=200)),
                ('admin_cleared_at', models.DateTimeField(blank=True, null=True)),
                ('admin_notes', models.TextField(blank=True, default='')),
                # HR section
                ('hr_cleared', models.BooleanField(default=False)),
                ('hr_cleared_by', models.CharField(blank=True, default='', max_length=200)),
                ('hr_cleared_at', models.DateTimeField(blank=True, null=True)),
                ('hr_notes', models.TextField(blank=True, default='')),
                # Manager section
                ('manager_cleared', models.BooleanField(default=False)),
                ('manager_cleared_by', models.CharField(blank=True, default='', max_length=200)),
                ('manager_cleared_at', models.DateTimeField(blank=True, null=True)),
                ('manager_notes', models.TextField(blank=True, default='')),
                ('notes', models.TextField(blank=True, default='')),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('complete', 'Complete')],
                    default='pending', max_length=15)),
            ],
            options={'db_table': 'exit_clearances'},
        ),
    ]
