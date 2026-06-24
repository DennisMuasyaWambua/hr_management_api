from django.apps import AppConfig


class WorkflowsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workflows'
    label = 'workflows'
    verbose_name = 'Workflow Automation'

    def ready(self):
        from django.db.models.signals import post_save, pre_save

        import apps.workflows.executors  # noqa: F401 — registers executor classes

        from apps.hr.models import EmployeeExit, LeaveRequest
        from apps.payroll.models import EmployeeProfile
        from apps.recruitment.models import Candidate, Interview

        from . import signals

        pre_save.connect(signals.candidate_pre_save, sender=Candidate)
        post_save.connect(signals.candidate_post_save, sender=Candidate)
        pre_save.connect(signals.interview_pre_save, sender=Interview)
        post_save.connect(signals.interview_post_save, sender=Interview)
        pre_save.connect(signals.leave_pre_save, sender=LeaveRequest)
        post_save.connect(signals.leave_post_save, sender=LeaveRequest)
        post_save.connect(signals.employee_profile_post_save, sender=EmployeeProfile)
        post_save.connect(signals.employee_exit_post_save, sender=EmployeeExit)
