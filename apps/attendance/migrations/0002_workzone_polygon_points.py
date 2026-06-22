from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workzone',
            name='polygon_points',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='List of {lat, lng} objects defining a polygon boundary. '
                          'When set, overrides center_lat/center_lng/radius_m for '
                          'containment checks.',
            ),
        ),
    ]
