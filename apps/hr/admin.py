from django.contrib import admin

from .models import (AllowanceType, ComplianceAlert, DeductionType,
                     DisciplinaryRecord, EmployeeAllowance, EmployeeCertificate,
                     EmployeeDeduction, EmployeeExit, ExitClearanceItem,
                     LeaveRecall, MinimumWage, OvertimeRequest, Reimbursement,
                     StatutoryRate)

for m in (AllowanceType, EmployeeAllowance, DeductionType, EmployeeDeduction,
          OvertimeRequest, Reimbursement, StatutoryRate, MinimumWage,
          ComplianceAlert, DisciplinaryRecord, EmployeeExit, ExitClearanceItem,
          LeaveRecall, EmployeeCertificate):
    admin.site.register(m)
