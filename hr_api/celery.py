"""
Celery configuration for HR-API project.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_api.settings')

app = Celery('hr_api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
