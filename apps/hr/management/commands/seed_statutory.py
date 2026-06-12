"""
Seed Kenyan statutory rates (2024/2025 framework) and indicative minimum
wages by job category (Regulation of Wages (General) (Amendment) Order 2024).

Run: python manage.py seed_statutory
Idempotent. Super admin can edit/version these later via api/statutory-rates/
without code changes — that is the whole point of the page (01-Jun session).

NOTE: minimum wage figures must be verified against the current gazette
before production use (action item: "Research Kenyan minimum wage").
"""
import datetime

from django.core.management.base import BaseCommand

from apps.hr.models import MinimumWage, StatutoryRate

EFFECTIVE = datetime.date(2024, 7, 1)

RATES = {
    'paye_bands': {
        'bands': [
            {'upto': 24000, 'rate': 0.10},
            {'upto': 32333, 'rate': 0.25},
            {'upto': 500000, 'rate': 0.30},
            {'upto': 800000, 'rate': 0.325},
            {'upto': None, 'rate': 0.35},
        ],
        'personal_relief': 2400,
    },
    'nssf': {'tier1_max': 7000, 'tier2_max': 36000, 'rate': 0.06},
    'shif': {'rate': 0.0275, 'minimum': 300},
    'housing_levy': {'rate': 0.015},
    'vat': {'rate': 0.16},
}

# Monthly KES, 'general' region tier (cities tier is higher). Indicative.
MINIMUM_WAGES = [
    ('general labourer', 15201.65),
    ('cleaner / sweeper / gardener', 15201.65),
    ('house servant / domestic worker', 15201.65),
    ('watchman / day guard', 16959.78),
    ('night watchman', 18929.46),
    ('machine attendant', 16417.85),
    ('cook / waiter', 17404.39),
    ('driver (light vehicle)', 19467.61),
    ('driver (medium vehicle)', 20021.74),
    ('driver (heavy commercial)', 24983.66),
    ('clerk / cashier', 26395.05),
    ('salesperson / shop assistant', 19810.59),
    ('machinist', 23420.66),
    ('artisan (ungraded)', 19810.59),
    ('artisan grade I', 28809.78),
]


class Command(BaseCommand):
    help = 'Seed Kenyan statutory rates and minimum wages'

    def handle(self, *args, **options):
        created_rates = 0
        for kind, value in RATES.items():
            _, created = StatutoryRate.objects.get_or_create(
                kind=kind, company_id=None, effective_from=EFFECTIVE,
                defaults={'value': value,
                          'note': 'Seeded 2024/25 framework — verify before production'})
            created_rates += int(created)

        created_wages = 0
        for category, amount in MINIMUM_WAGES:
            _, created = MinimumWage.objects.get_or_create(
                job_category=category, region='general',
                effective_from=EFFECTIVE,
                defaults={'monthly_amount': amount,
                          'source': 'Regulation of Wages (General)(Amendment) Order 2024 — indicative, verify'})
            created_wages += int(created)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {created_rates} statutory rates, {created_wages} minimum wages.'))
