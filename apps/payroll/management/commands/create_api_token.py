"""
Management command to create an API token for the HR dashboard.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()


class Command(BaseCommand):
    help = 'Create an API token for a service account'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='hr_dashboard_service',
            help='Username for the service account (default: hr_dashboard_service)'
        )
        parser.add_argument(
            '--email',
            default='service@hr-dashboard.local',
            help='Email for the service account'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']

        # Create or get the service user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_active': True,
            }
        )

        if created:
            # Set an unusable password for service accounts
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created service user: {username}'))
        else:
            self.stdout.write(f'Using existing user: {username}')

        # Create or get the token
        token, token_created = Token.objects.get_or_create(user=user)

        if token_created:
            self.stdout.write(self.style.SUCCESS('Created new API token'))
        else:
            self.stdout.write('Using existing API token')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'API Token: {token.key}'))
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write('')
        self.stdout.write('Add this to your .env file:')
        self.stdout.write(self.style.SUCCESS(f'HR_API_TOKEN={token.key}'))
