from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0004_kpiassignment_medicalrecord_performancereview_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='backgroundcheck',
            name='validation_body_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='backgroundcheck',
            name='validation_body_email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='backgroundcheck',
            name='docuseal_submission_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='backgroundcheck',
            name='signed_document_url',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='backgroundcheck',
            name='verdict',
            field=models.CharField(
                blank=True,
                choices=[('clean', 'Clean'), ('not_clean', 'Not Clean')],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='backgroundcheck',
            name='reviewer_comments',
            field=models.TextField(blank=True, null=True),
        ),
    ]
