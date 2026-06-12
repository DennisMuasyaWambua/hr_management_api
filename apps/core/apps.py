from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core (RBAC, Notifications, Documents)'

    def ready(self):
        # Register drf-spectacular auth scheme for ServiceKeyAuthentication
        from . import schema  # noqa: F401
