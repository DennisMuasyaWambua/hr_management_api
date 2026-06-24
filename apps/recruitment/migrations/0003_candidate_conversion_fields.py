from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0002_interview'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='converted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='converted_employee_id',
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
