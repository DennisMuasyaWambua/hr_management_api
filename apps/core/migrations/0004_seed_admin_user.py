from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_admin(apps, schema_editor):
    User = apps.get_model('auth', 'User')

    hashed = make_password('dennis123')

    # Update if exists, create if not — pure SQL-level operations only,
    # no model instance methods, so this works safely in migration context.
    if User.objects.filter(email='wamuasya23@gmail.com').exists():
        User.objects.filter(email='wamuasya23@gmail.com').update(
            password=hashed,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
    else:
        User.objects.create(
            username='wamuasya23',
            email='wamuasya23@gmail.com',
            first_name='Dennis',
            last_name='Wambua',
            password=hashed,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_otptoken_appuser'),
    ]

    operations = [
        migrations.RunPython(seed_admin, reverse_seed),
    ]
