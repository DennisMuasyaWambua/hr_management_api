import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_seed_admin_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaffAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('staff_user_id', models.UUIDField(db_index=True)),
                ('employee_id', models.UUIDField(db_index=True)),
                ('assigned_by', models.UUIDField(blank=True, null=True)),
            ],
            options={
                'db_table': 'rbac_staff_assignments',
                'unique_together': {('staff_user_id', 'employee_id')},
            },
        ),
    ]
