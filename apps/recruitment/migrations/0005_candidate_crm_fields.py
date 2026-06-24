from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0004_candidate_recruiter_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='is_passive',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='candidate',
            name='availability_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='location',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='experience_years',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='education_level',
            field=models.CharField(
                blank=True, max_length=20, null=True,
                choices=[
                    ('high_school', 'High School'), ('bachelors', 'Bachelors'),
                    ('masters', 'Masters'), ('phd', 'PhD'), ('other', 'Other'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='candidate',
            name='linkedin_url',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='skills',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
