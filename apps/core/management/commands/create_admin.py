"""
Creates (or updates) the admin superuser from env vars.
Run automatically on every Railway release via the Procfile.

Required env vars:
  ADMIN_EMAIL     e.g. wamuasya23@gmail.com
  ADMIN_PASSWORD  e.g. dennis123

If a user with that email already exists the password is updated in place.
Skipped silently when either var is absent.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decouple import config


class Command(BaseCommand):
    help = 'Ensure admin superuser exists (idempotent, driven by env vars)'

    def handle(self, *args, **options):
        email    = config('ADMIN_EMAIL', default='').strip()
        password = config('ADMIN_PASSWORD', default='').strip()

        if not email or not password:
            self.stdout.write('ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping.')
            return

        User = get_user_model()
        # Never use get_or_create(email=...) here: if an email is duplicated
        # (e.g. a dashboard-created user plus a previous admin seed) it raises
        # MultipleObjectsReturned and crashes the Railway release step, which
        # leaves the deploy unpromoted and every request 502s. Pick the
        # existing user defensively instead.
        existing = User.objects.filter(email=email).order_by('id')
        user = existing.first()
        created = user is None
        if created:
            user = User(username=email, email=email,
                        first_name='Admin', last_name='')
        else:
            extra = existing.exclude(pk=user.pk)
            if extra.exists():
                self.stdout.write(self.style.WARNING(
                    f'Found {extra.count()} duplicate user(s) for {email}; '
                    f'keeping id={user.pk} and ignoring the rest.'))
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        from apps.core.models import AppUser
        AppUser.objects.get_or_create(
            auth_user=user,
            defaults={
                'full_name': user.get_full_name() or email,
                'email': email,
                'role': 'super_admin',
                'is_active': True,
                'preferred_language': 'en',
            },
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} admin user: {email}'))
