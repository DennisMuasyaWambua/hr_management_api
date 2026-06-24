from django.apps import AppConfig


class ActionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.actions'
    verbose_name = 'Action Center'

    def ready(self):
        # Import all generator modules so their @register_generator decorators fire.
        # Order determines the default sort within equal priority scores.
        import apps.actions.generators.recruitment      # noqa: F401
        import apps.actions.generators.leave            # noqa: F401
        import apps.actions.generators.onboarding       # noqa: F401
        import apps.actions.generators.employee_lifecycle  # noqa: F401
        import apps.actions.generators.offboarding      # noqa: F401
        import apps.actions.generators.compliance       # noqa: F401
        import apps.actions.generators.workflow          # noqa: F401
