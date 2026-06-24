# ERP Gap Analysis — Sheer Logic HR Platform
Generated: 2026-06-24

---

## 1. What Already Exists (Production-Ready)

| Module | Status | Key Models / Endpoints |
|--------|--------|----------------------|
| RBAC & Audit | ✅ Complete | Role, Permission, RolePermission, UserRoleAssignment, StaffAssignment, ServiceAuditLog |
| Authentication | ✅ Complete | Token, OTP, ServiceKey, AppUser, face/SmileID |
| Payroll Cycle | ✅ Complete | PayrollRun, PayrollRecord, PaymentBatch, ApproverConfig, M-of-N approval, PesaPal/IntaSend/Daraja disbursement |
| Tax Calculation | ✅ Complete | StatutoryRate (versioned), PAYE/NSSF/SHIF/HousingLevy calculator |
| Leave Management | ✅ Functional | LeaveRequest, LeaveBalance, LeaveRecall, OvertimeRequest |
| Attendance | ✅ Functional | AttendanceEvent (TimescaleDB-optional), WorkZone geofencing, face check-in |
| Recruitment | ✅ Functional | JobPosting, Candidate (GROQ AI scoring), Interview, public careers portal, job alerts |
| Performance | ✅ Partial | PerformanceReview, KpiAssignment (JSON targets/scores) |
| Training | ✅ Partial | TrainingSession, TrainingEnrollment |
| Exit Management | ✅ Partial | EmployeeExit, ExitClearance (IT/Finance/Admin/HR/Manager sign-offs) |
| Compliance | ✅ Partial | ComplianceAlert, BackgroundCheck (DocuSeal e-sig), DisciplinaryRecord, EmployeeCertificate |
| Onboarding | ✅ Partial | EmployeeOnboardingDocument (6-item checklist) |
| Notifications | ✅ Complete | Email (SMTP/EmailJS), SMS (Africa's Talking), WhatsApp, 14 event templates |
| Action Center | ✅ Complete | 7 generator types, priority scoring, caching, dismiss/escalate |
| Document Generation | ✅ Complete | Payslip PDF (ReportLab), Excel summaries, DocuSeal signing |

---

## 2. Gap Analysis by Phase

### Phase 1 — Workflow Automation Engine
**Current state**: Hardcoded state machines only (payroll draft→calculated→approved, leave pending→approved)  
**Missing**:
- No configurable triggers → conditions → actions chains
- No conditional branching or field comparisons
- No delay/scheduling support
- No execution history or retry logic
- No delegation or escalation paths
- No cross-module workflow templates

**What to build**: `apps/workflows/` — WorkflowDefinition, WorkflowCondition, WorkflowAction, WorkflowExecution, WorkflowExecutionLog, WorkflowTask

---

### Phase 2 — ATS Candidate CRM
**Current state**: Candidate model has stage/notes/cv but no structured CRM layer  
**Missing**:
- No talent pools (saved candidate collections)
- No candidate tags
- No activity timeline (email/call/note history)
- No referral tracking
- No passive candidate flag with availability date
- No structured skills/education/experience records
- No advanced search (by skill, location, experience, availability)
- No CandidateScore breakdown (skill/exp/industry/location)

**What to build**: TalentPool, TalentPoolMember, CandidateTag, CandidateNote, CandidateActivity, Referral — plus Candidate model extensions

---

### Phase 3 — Recruitment Client CRM
**Current state**: Nothing — no client/contact management at all  
**Missing**:
- Client organizations and contacts
- Hiring manager assignments
- Service contracts and SLA definitions
- Meeting notes
- Client pipeline stages (Lead→Active→Dormant)
- Placement tracking and revenue

**What to build**: `apps/crm/` — RecruitmentClient, ClientContact, HiringManager, ClientContract, ClientSLA, ClientMeetingNote, Placement

---

### Phase 4 — AI Matching Engine
**Current state**: One-way only — GROQ scores candidates against a job; no two-way matching  
**Missing**:
- No employee ↔ vacancy matching
- No weighted multi-dimension scoring (skill/exp/industry/location)
- No recommendation engine
- No adapter pattern for future AI providers
- No match result persistence

**What to build**: `apps/matching/` — MatchResult, skill/experience/industry/location scorers, RuleBasedProvider, provider adapters (OpenAI stub, LocalLLM stub)

---

### Phase 5 — Executive Analytics
**Current state**: View stubs exist (`WorkforceAnalyticsView`, `DashboardSummaryView`) but have minimal implementation  
**Missing**:
- No time-to-hire metrics
- No offer acceptance rates
- No pipeline conversion rates
- No headcount/turnover/probation analytics
- No payroll cost by department
- No client success metrics
- No caching of expensive aggregates

**What to build**: `apps/analytics/` — aggregation services with Redis caching, time-series metrics

---

### Phase 6 — Learning Management System
**Current state**: TrainingSession + TrainingEnrollment (metadata only, no content)  
**Missing**:
- No course content structure (modules, lessons)
- No assessments or quizzes
- No progress tracking (% complete)
- No prerequisite chains
- No learning paths
- No automated certificate issuance
- No compliance reporting (who completed mandatory training)

**What to build**: `apps/lms/` — Course, CourseModule, Lesson, Assessment, AssessmentQuestion, Enrollment, LessonProgress, LearningPath, LMSCertificate

---

### Phase 7 — Advanced Performance Management
**Current state**: PerformanceReview (free-form rating) + KpiAssignment (JSON targets) — no workflow  
**Missing**:
- No structured goal-setting workflow
- No competency framework
- No 360° multi-rater feedback
- No development plans
- No review calibration
- No succession planning
- No Action Center integration for review cycles

**What to build**: PerformanceGoal, GoalUpdate, Competency, CompetencyAssessment, DevelopmentPlan, DevelopmentActivity, FeedbackRequest, Feedback360Response

---

## 3. Dependency Order for Implementation

```
Phase 1 (Workflow Engine)  ← no new dependencies
    ↓
Phase 2 (Candidate CRM)   ← extends recruitment models
    ↓
Phase 3 (Client CRM)      ← new app, references recruitment
    ↓
Phase 4 (AI Matching)     ← requires Phase 2 (skills/CandidateScore)
    ↓
Phase 5 (Analytics)       ← requires Phase 2+3 for full metrics
    ↓
Phase 6 (LMS)             ← standalone, references EmployeeProfile
    ↓
Phase 7 (Performance)     ← extends hr models, integrates with Phase 1 workflow
```

---

## 4. Architecture Conventions to Maintain

1. **Company isolation**: Every new model must have `company_id` UUID field with `db_index=True`
2. **TenantStamped**: New HR-adjacent models should extend the abstract `TenantStamped` base or replicate its fields
3. **RBAC**: Every view must use `HasModulePermission` with a new module slug added to `seed_rbac.py` and a migration
4. **Audit logging**: All mutation endpoints must call `ServiceAuditLog.log()`
5. **Notifications**: Use `notify()` from `apps.core.services.notifications` — never direct SMTP calls
6. **Serializers**: Use DRF ModelSerializer; avoid `__all__` — be explicit about fields
7. **Pagination**: All list endpoints use the project's `PageNumberPagination`
8. **Migrations**: Each new app gets its own migration sequence; cross-app FK migrations must list both apps in `dependencies`
9. **Tests**: Django TestCase + DRF APITestCase; mock external calls; use `force_authenticate`

---

## 5. RBAC Modules to Add

| Phase | Module Slug | Grants to |
|-------|------------|-----------|
| 1 | `workflows` | internal_hr, deployed_hr, company_admin |
| 2 | `talent_pools`, `referrals` | internal_hr, deployed_hr |
| 3 | `crm` | internal_hr, company_admin |
| 4 | `matching` | internal_hr, deployed_hr |
| 5 | `analytics` | internal_hr, company_admin |
| 6 | `lms` | internal_hr, deployed_hr, white_collar_employee, blue_collar_employee |
| 7 | `goals`, `feedback` | internal_hr, deployed_hr, internal_manager, deployed_manager |
