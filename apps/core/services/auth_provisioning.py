"""
Employee login provisioning, shared by password login (AuthLoginView) and
OTP login (SendOTPView/VerifyOTPView).

employee_profiles has no email column (that lived on Supabase's `users`
table, which doesn't exist on Railway), so an employee can only log in once
an `AppUser` directory row exists for their email — created either by the
one-time Supabase data restore, by HR via the dashboard's user management,
or by a seed script. This function does NOT create that row from thin air;
it only lazily creates the Django auth.User + Token the first time someone
with an existing AppUser row actually logs in, so we don't need a big
upfront backfill migration.
"""
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string

from apps.core.models import AppUser

User = get_user_model()


def resolve_or_provision_login_user(email: str):
    """Returns a Django auth.User for this email, or None if there's no
    AppUser directory entry for it (nothing to log in as)."""
    email = (email or '').strip().lower()
    if not email:
        return None

    app_user = AppUser.objects.filter(email__iexact=email, is_deleted=False).first()
    if not app_user:
        return None

    if app_user.auth_user_id:
        return app_user.auth_user

    django_user = User.objects.create_user(
        username=email, email=email, password=get_random_string(32),
        first_name=(app_user.full_name or '').split(' ')[0][:30],
    )
    app_user.auth_user = django_user
    app_user.save(update_fields=['auth_user'])
    return django_user
