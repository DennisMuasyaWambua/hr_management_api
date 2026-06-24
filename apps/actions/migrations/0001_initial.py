import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ActionRecord',
            fields=[
                ('id', models.CharField(max_length=200, primary_key=True, serialize=False)),
                ('company_id', models.UUIDField(db_index=True)),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('dismissed_at', models.DateTimeField(blank=True, null=True)),
                ('dismissed_by', models.UUIDField(blank=True, null=True)),
                ('dismiss_reason', models.TextField(blank=True, default='')),
                ('escalated_at', models.DateTimeField(blank=True, null=True)),
                ('escalated_by', models.UUIDField(blank=True, null=True)),
                ('escalate_note', models.TextField(blank=True, default='')),
                ('notification_sent_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'action_records',
            },
        ),
    ]
