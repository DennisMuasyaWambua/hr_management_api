from django.db import migrations


class Migration(migrations.Migration):
    """
    Composite indexes on source-model tables used by Action Center generators.
    Uses RunSQL so there are no cross-app model dependencies.
    All statements are idempotent (IF NOT EXISTS).
    """

    dependencies = [
        ('actions', '0001_initial'),
        ('recruitment', '0002_interview'),
        ('hr', '0004_kpiassignment_medicalrecord_performancereview_and_more'),
        ('payroll', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_interviews_company_status_scheduled
                    ON interviews (company_id, status, scheduled_at);

                CREATE INDEX IF NOT EXISTS idx_candidates_company_stage_updated
                    ON candidates (company_id, current_stage, updated_at);

                CREATE INDEX IF NOT EXISTS idx_onboarding_docs_employee_status
                    ON employee_onboarding_documents (employee_id, status);

                CREATE INDEX IF NOT EXISTS idx_employee_profiles_company_status_enddate
                    ON employee_profiles (company_id, employment_status, end_date);

                CREATE INDEX IF NOT EXISTS idx_certificates_company_expiry
                    ON employee_certificates (company_id, expiry_date);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_interviews_company_status_scheduled;
                DROP INDEX IF EXISTS idx_candidates_company_stage_updated;
                DROP INDEX IF EXISTS idx_onboarding_docs_employee_status;
                DROP INDEX IF EXISTS idx_employee_profiles_company_status_enddate;
                DROP INDEX IF EXISTS idx_certificates_company_expiry;
            """,
        ),
    ]
