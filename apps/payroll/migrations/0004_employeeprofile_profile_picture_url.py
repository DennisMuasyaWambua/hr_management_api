from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0003_payrollapproval_signature_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='profile_picture_url',
            field=models.TextField(blank=True, null=True),
        ),
    ]
