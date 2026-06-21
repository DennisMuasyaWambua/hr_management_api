from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='worker_class',
            field=models.CharField(
                choices=[('white_collar', 'White Collar'),
                         ('blue_collar', 'Blue Collar')],
                default='white_collar',
                max_length=20,
            ),
        ),
    ]
