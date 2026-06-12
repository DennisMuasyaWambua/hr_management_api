"""
Database router: when TIMESCALE_ENABLED, all apps.attendance models live in
the 'timescale' database alias (a Postgres instance with the timescaledb
extension). Otherwise everything stays on 'default' and nothing changes.
"""
from django.conf import settings


class TimescaleRouter:
    app_label = 'attendance'

    def _enabled(self):
        return getattr(settings, 'TIMESCALE_ENABLED', False) and \
            'timescale' in settings.DATABASES

    def db_for_read(self, model, **hints):
        if self._enabled() and model._meta.app_label == self.app_label:
            return 'timescale'
        return None

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app_label:
            return db == ('timescale' if self._enabled() else 'default')
        if db == 'timescale':
            return False
        return None
