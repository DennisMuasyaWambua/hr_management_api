"""
Employee email-OTP login (the PWA's primary login path — matches the old
`supabase.auth.signInWithOtp({email})`/`verifyOtp`). Password login for
HR/admin users lives in apps.payroll.views.AuthLoginView; this is additive,
not a replacement.
"""
import random

from django.utils import timezone
from rest_framework import views
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.models import OTPToken
from apps.core.services.auth_provisioning import resolve_or_provision_login_user
from apps.core.services.notifications import send_email

OTP_TTL_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60


def _login_payload(user, token):
    profile = getattr(user, 'hr_profile', None)
    # X-User-Id must be a UUID (ServiceAuditLog.actor_user_id etc.) — use the
    # AppUser ("hr_profile") UUID, not Django auth.User's int id.
    user_id = str(profile.id) if profile else str(user.id)
    return {
        'token': token.key,
        'user_id': user_id,
        'email': user.email,
        'full_name': getattr(profile, 'full_name', '') or user.get_full_name() or user.username,
        'role': getattr(profile, 'role', 'employee'),
        'company_id': str(getattr(profile, 'company_id', '') or ''),
        'employee_id': str(getattr(profile, 'employee_id', '') or ''),
    }


class SendOTPView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'error': 'email is required'}, status=400)

        recent = OTPToken.objects.filter(email=email).order_by('-created_at').first()
        if recent and (timezone.now() - recent.created_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
            return Response({'error': 'Please wait before requesting another code.'}, status=429)

        code = f'{random.randint(0, 999999):06d}'
        OTPToken.objects.create(
            email=email, code=code,
            expires_at=timezone.now() + timezone.timedelta(minutes=OTP_TTL_MINUTES),
        )
        send_email(email, 'Your sign-in code',
                  f'Your sign-in code is {code}. It expires in {OTP_TTL_MINUTES} minutes.')
        return Response({'success': True})


class VerifyOTPView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        code = (request.data.get('code') or '').strip()
        if not email or not code:
            return Response({'error': 'email and code are required'}, status=400)

        otp = OTPToken.objects.filter(email=email).order_by('-created_at').first()
        if not otp or not otp.is_valid:
            return Response({'error': 'Code expired or not found. Request a new one.'}, status=400)

        if otp.code != code:
            otp.attempts += 1
            otp.save(update_fields=['attempts'])
            return Response({'error': 'Incorrect code.'}, status=400)

        otp.consumed_at = timezone.now()
        otp.save(update_fields=['consumed_at'])

        user = resolve_or_provision_login_user(email)
        if not user:
            return Response({'error': 'No account found for this email.'}, status=404)
        if not user.is_active:
            return Response({'error': 'Account is inactive'}, status=403)

        token, _ = Token.objects.get_or_create(user=user)
        return Response(_login_payload(user, token))
