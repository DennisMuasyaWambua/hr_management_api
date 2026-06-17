from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_admin(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    AppUser = apps.get_model('core', 'AppUser')

    user, created = User.objects.get_or_create(
        email='wamuasya23@gmail.com',
        defaults={
            'username': 'wamuasya23',
            'first_name': 'Dennis',
            'last_name': 'Wambua',
            'password': make_password('dennis123'),
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        },
    )
    if not created:
        # Already exists — just ensure password and flags are correct
        user.set_password('dennis123')
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

    AppUser.objects.get_or_create(
        email='wamuasya23@gmail.com',
        defaults={
            'auth_user': user,
            'full_name': 'Dennis Wambua',
            'role': 'super_admin',
            'is_active': True,
            'preferred_language': 'en',
        },
    )


def reverse_seed(apps, schema_editor):
    pass  # non-destructive reverse — leave the user in place


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_otptoken_appuser'),
    ]

    operations = [
        migrations.RunPython(seed_admin, reverse_seed),
    ]
