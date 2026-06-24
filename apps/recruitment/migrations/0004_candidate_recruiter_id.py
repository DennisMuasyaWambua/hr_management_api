from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0003_candidate_conversion_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='recruiter_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
