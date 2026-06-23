"""
Management command: seed_hires
Distributes existing active employee start_dates across the last 12 months
so the Reports → Monthly Hires chart shows realistic activity.

Usage:
    python manage.py seed_hires
    python manage.py seed_hires --reset   # restore all start_dates to 2023-01-01
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.payroll.models import EmployeeProfile


# Realistic monthly hire volumes (relative weights, sums to 100)
MONTHLY_WEIGHTS = [3, 5, 8, 7, 10, 9, 6, 11, 13, 10, 9, 9]  # Jul→Jun


class Command(BaseCommand):
    help = "Seed employee start_dates across the last 12 months for a realistic hires chart"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all start_dates back to 2023-01-01",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            EmployeeProfile.objects.filter(is_deleted=False).update(
                start_date=date(2023, 1, 1)
            )
            self.stdout.write(self.style.SUCCESS("Reset all start_dates to 2023-01-01"))
            return

        today = date.today()
        # Build ordered list of (year, month) for the last 12 months
        months = []
        for i in range(11, -1, -1):
            d = date(today.year, today.month, 1) - timedelta(days=i * 28)
            months.append((d.year, d.month))

        profiles = list(
            EmployeeProfile.objects.filter(is_deleted=False).order_by("employee_number")
        )
        if not profiles:
            self.stdout.write(self.style.WARNING("No employee profiles found — nothing to seed."))
            return

        # Assign months using weighted distribution
        weights = MONTHLY_WEIGHTS[-len(months):]
        assigned_months = random.choices(months, weights=weights, k=len(profiles))

        for profile, (yr, mo) in zip(profiles, assigned_months):
            # Random day within the month
            day = random.randint(1, 28)
            profile.start_date = date(yr, mo, day)

        EmployeeProfile.objects.bulk_update(profiles, ["start_date"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {len(profiles)} employee start_dates across {len(months)} months."
            )
        )
        # Print distribution summary
        from collections import Counter
        dist = Counter((p.start_date.year, p.start_date.month) for p in profiles)
        for yr, mo in months:
            label = date(yr, mo, 1).strftime("%b %Y")
            count = dist.get((yr, mo), 0)
            bar = "█" * count
            self.stdout.write(f"  {label}: {bar} ({count})")
