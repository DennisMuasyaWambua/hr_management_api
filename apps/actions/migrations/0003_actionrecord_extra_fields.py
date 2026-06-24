import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0002_action_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionrecord',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='actionrecord',
            name='resolved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='actionrecord',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
