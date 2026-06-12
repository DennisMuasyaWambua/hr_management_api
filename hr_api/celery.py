"""
Celery configuration for HR-API project.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_api.settings')

app = Celery('hr_api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Variable allowances (per diem) reset at month end — 1st 00:05
    'reset-variable-allowances': {
        'task': 'apps.hr.tasks.reset_variable_allowances',
        'schedule': crontab(minute=5, hour=0, day_of_month=1),
    },
    # Certificate expiry alerts to HR — daily 07:00
    'certificate-expiry-alerts': {
        'task': 'apps.hr.tasks.certificate_expiry_alerts',
        'schedule': crontab(minute=0, hour=7),
    },
    # Attendance below 30% report — daily 10:00
    'low-attendance-report': {
        'task': 'apps.attendance.tasks.low_attendance_report',
        'schedule': crontab(minute=0, hour=10),
    },
}
