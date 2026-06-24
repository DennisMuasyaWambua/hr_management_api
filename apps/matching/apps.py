from django.apps import AppConfig


class MatchingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.matching'
    label = 'matching'
    verbose_name = 'AI Matching Engine'

    def ready(self):
        import apps.matching.providers.rule_based  # noqa: F401 — registers provider
