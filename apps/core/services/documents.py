# Canonical location moved to apps/payroll/services/documents.
# This shim keeps existing imports working without changes.
from apps.payroll.services.documents import (  # noqa: F401
    BRAND, BRAND_LIGHT,
    sha256_of, generate_payroll_pdf, generate_payslip_pdf,
    password_protect_pdf, generate_payroll_excel,
)
