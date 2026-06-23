from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0004_employeeprofile_profile_picture_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='face_descriptor',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
