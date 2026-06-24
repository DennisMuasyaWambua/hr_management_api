# Frontend Gap Analysis

**Date:** 2026-06-24  
**Scope:** What API capabilities are needed to fully power the Next.js PWA front-end

This document maps every major frontend screen/flow to the backend API, identifying what exists, what's incomplete, and what's entirely missing.

---

## Architecture Context

- **Frontend:** Next.js (separate repo), deployed on Vercel at `hr-system-dashboard-sheerlogic.vercel.app`
- **API calls:** Next.js route handlers call this API with `X-Service-Key` (server-to-server) and forward identity headers (`X-User-Id`, `X-User-Role`, `X-Company-Id`)
- **Auth flow:** Email OTP → `POST /api/auth/send-otp/` → `POST /api/auth/verify-otp/` → token stored in Next.js session
- **No frontend code exists in this repo** — frontend is entirely separate

---

## 1. Login / Auth Screens

### Screens
- OTP email input, OTP code entry, dashboard redirect

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Send OTP | `POST /api/auth/send-otp/` | ✅ |
| Verify OTP + get token | `POST /api/auth/verify-otp/` | ✅ |
| Password login (admin) | `POST /api/auth/login/` | ✅ |
| Logout / invalidate token | — | ❌ Missing |
| Forgot password email | — | ❌ Missing |
| Refresh expired token | — | ❌ Missing (tokens never expire) |
| Get current user details | `GET /api/me/` | ⚠️ Minimal — no company name, employee details |

### Gaps
- **No logout** — frontend cannot clear a token server-side (only client-side removal)
- **No token expiry** — a compromised token is valid indefinitely
- **`/api/me/` returns only user identity** — missing: employee name, department, profile picture URL, company name, company logo

---

## 2. HR Dashboard (HR Manager view)

### Screens
- Overview KPIs, headcount chart, new hires, open positions, pending actions

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| 8-KPI snapshot | `GET /api/analytics/overview/` | ✅ |
| Headcount by dept / monthly hires | `GET /api/analytics/headcount/` | ✅ |
| Pending actions (smart alerts) | `GET /api/actions/` | ✅ |
| Dismiss / escalate action | `POST /api/actions/{id}/dismiss/` | ✅ |
| Payroll run status | `GET /api/payroll-runs/` | ✅ |
| Recent announcements | `GET /api/announcements/` | ✅ |

### Gaps
- **No "recently changed" feed** — no endpoint for activity stream (last 20 events across modules)
- **Analytics cache TTL 300s** — dashboard may show data up to 5 minutes stale

---

## 3. Employee Directory

### Screens
- Search / filter employees, employee profile card, org chart

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| List employees | `GET /api/employees/` | ✅ |
| Filter by dept / status / type | Query params on above | ✅ |
| Employee detail | `GET /api/employees/{id}/` | ✅ |
| Upload profile picture | `POST /api/profile-picture/` | ✅ |
| Employee org chart (manager hierarchy) | — | ❌ Missing |

### Gaps
- **No org chart endpoint** — `EmployeeProfile.manager_id` exists but no tree-building endpoint
- **No bulk employee import** — no CSV/Excel upload endpoint for onboarding multiple employees
- **Profile picture returns a URL** but if S3 is not configured the URL is a local filesystem path (broken in production)

---

## 4. Payroll Management

### Screens
- Payroll run list, run detail, approve/reject, payment status, payslip PDF

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| List payroll runs | `GET /api/payroll-runs/` | ✅ |
| Run detail with records | `GET /api/payroll-runs/{id}/details/` | ✅ |
| Submit for approval | `POST /api/payroll-runs/{id}/submit/` | ✅ |
| Approve / reject | `POST /api/payroll-runs/{id}/approve/` | ✅ |
| Mark as paid | `POST /api/payroll-runs/{id}/mark-paid/` | ✅ |
| Download payslip PDF | `GET /api/payroll/documents/{id}/` (FileField) | ⚠️ Exists but file URL may be broken without S3 |
| Employee payslip list | `GET /api/payslips/` | ✅ |
| Payroll trend analytics | `GET /api/analytics/payroll/` | ✅ |
| Payment batch status | `GET /api/payment-batches/` | ⚠️ Unclear if listed |

### Gaps
- **No run period creation wizard** — UI needs to know which employees are included before running
- **No statutory rate editor UI** — `StatutoryRateViewSet` exists but no frontend can safely edit tax brackets
- **No allowance/deduction bulk edit** — individual-record-only API for allowances/deductions
- **PDF download requires S3 configuration** — broken without it

---

## 5. Leave Management

### Screens
- Leave request form, manager inbox, calendar view, balances

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Apply for leave | `POST /api/leave/` | ✅ |
| Manager approve/reject | `PATCH /api/leave/{id}/` with status | ✅ |
| View leave balance | `GET /api/leave-balances/` | ✅ |
| Leave calendar (all team) | — | ❌ Missing |
| Leave recall | `POST /api/leave-recalls/` | ✅ |
| One-tap SMS approval | `POST /api/one-tap/{token}/` | ✅ |

### Gaps
- **No leave calendar endpoint** — `start_date` + `end_date` fields on `LeaveRequest` exist but no calendar-shape endpoint (date → [employees on leave])
- **No leave policy model** — leave types and entitlements are hardcoded; no company-level policy editor
- **No leave overlap check** — API doesn't reject overlapping leave requests for same employee

---

## 6. Attendance & Check-In (PWA Mobile)

### Screens
- Check-in button, GPS map, face scan, history list, violation alerts

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Check-in with GPS | `POST /api/attendance/check-in/` | ✅ |
| Location ping | `POST /api/attendance/ping/` | ✅ |
| Attendance history | `GET /api/attendance/events/` | ✅ |
| Today's check-in status | — | ❌ Missing |
| Geofence violation alerts | `GET /api/geofence-violations/` | ✅ |
| Submit out-of-zone reason | field on CheckIn | ✅ |
| Attendance rate analytics | `GET /api/attendance/rate/` | ✅ |

### Gaps
- **No `GET /api/attendance/today/`** — home screen can't show "checked in ✓" without querying full history
- **No shift schedule** — check-in can happen at any time; no enforcement of work hours
- **No timesheet summary** — no weekly/monthly hours worked aggregate for employee

---

## 7. Recruitment Pipeline

### Screens
- Job posting list, candidate kanban, interview scheduler, candidate profile

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Job postings CRUD | `CRUD /api/job-postings/` | ✅ |
| Candidate list / search | `GET /api/candidates/`, `GET /api/candidate-search/` | ✅ |
| Move candidate stage (kanban) | `PATCH /api/candidates/{id}/` with `current_stage` | ✅ |
| Schedule interview | `POST /api/interviews/` | ✅ |
| AI match score | `POST /api/matching/score/` | ✅ |
| Talent pools | `GET/POST /api/talent-pools/` | ✅ |
| Candidate notes | `POST /api/candidate-notes/` | ✅ |
| Candidate tags | `POST /api/candidate-tags/` | ✅ |
| Referrals | `GET/POST /api/referrals/` | ✅ |
| Recruitment funnel analytics | `GET /api/analytics/recruitment/` | ✅ |

### Gaps
- **No public apply endpoint** — candidates can't self-apply from a careers page
- **No offer letter generation** — after hire, no document generation for job offer
- **No resume/CV upload endpoint** — `resume_url` is a text field; no file upload
- **No background check initiation UI** — `BackgroundCheckViewSet` exists but no workflow for initiating checks

---

## 8. Client CRM (Staffing)

### Screens
- Client list, contract detail, meeting notes, placement tracker

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Clients CRUD (soft-delete) | `CRUD /api/clients/` | ✅ |
| Client contracts + SLAs | `CRUD /api/client-contracts/` (nested SLAs) | ✅ |
| Meeting notes | `GET/POST /api/clients/{id}/meeting-notes/` | ✅ |
| Placements | `CRUD /api/placements/` | ✅ |
| Placement analytics | `GET /api/analytics/placements/` | ✅ |
| Client contacts | `CRUD /api/client-contacts/` | ✅ |

### Gaps
- **No client portal** — clients have no login or read-only view of their placements/SLAs
- **No SLA breach alerting** — `ClientSLA` model has `status` field but no automatic alert on breach

---

## 9. LMS (Learning Management)

### Screens
- Course catalogue, lesson player, assessment, certificate

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Course catalogue | `GET /api/lms/courses/` | ✅ |
| Enrol in course | `POST /api/lms/enrollments/` | ✅ |
| Mark lesson complete | `POST /api/lms/enrollments/{id}/complete-lesson/` | ✅ |
| Submit assessment | `POST /api/lms/enrollments/{id}/submit-assessment/` | ✅ |
| View certificate | `GET /api/lms/certificates/` | ✅ |
| Learning path | `GET /api/lms/learning-paths/` | ✅ |

### Gaps
- **No video streaming** — `video_url` is a raw URL field; no signed URL generation, bandwidth throttling, or HLS support
- **No SCORM player support** — `lesson_type='scorm'` exists but no SCORM API endpoint or package upload
- **No course rating** — employees can't rate courses
- **No progress resume** — lesson progress tracked but no "continue where you left off" endpoint
- **Certificate PDF generation** — `pdf_url` is nullable; no actual PDF generation on certificate issuance

---

## 10. Performance Management

### Screens
- Goal dashboard, check-in form, competency radar, IDP editor, 360 review

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| Goals CRUD + check-ins | `CRUD /api/performance/goals/` + `/updates/` | ✅ |
| Competency catalogue | `CRUD /api/performance/competencies/` | ✅ |
| Rate competency | `POST /api/performance/competency-ratings/` | ✅ |
| IDP editor | `CRUD /api/performance/development-plans/` | ✅ |
| 360 request + respond | `POST /api/performance/feedback-requests/` | ✅ |
| Anonymous response view | `GET /api/performance/feedback-requests/{id}/responses/` | ✅ |

### Gaps
- **No performance cycle management** — no model for "review cycle" configuration; review cycles are free-text strings
- **No calibration / forced ranking** — no team-level goal comparison
- **Integration with LMS** — `DevelopmentPlanItem.course_id` is a UUID reference but no endpoint to auto-enrol from IDP
- **No manager view of direct reports' goals** — filtering by employee_id works but no "team goals" summary

---

## 11. Notifications & Inbox

### Screens
- Notification bell, inbox list, mark-as-read

### API Status

| Need | Endpoint | Status |
|------|----------|--------|
| List notifications | `GET /api/notifications/` (NotificationLog) | ✅ |
| Notification count | — | ❌ Missing |
| Mark as read | — | ❌ Missing |
| Push subscription | — | ❌ Missing |
| Real-time (WebSocket/SSE) | — | ❌ Missing |

### Gaps
This is the most underdeveloped area relative to frontend needs.

---

## 12. Summary: Missing Endpoints by Priority

### Priority 1 — Blocks basic functionality
| Endpoint | Blocker for |
|----------|-------------|
| `POST /api/auth/logout/` | All authenticated screens |
| `GET /api/employees/me/` | Every screen needing employee name/dept |
| `GET /api/attendance/today/` | Blue-collar home screen |
| `GET /api/notifications/unread-count/` | Notification badge |
| `POST /api/notifications/{id}/read/` | Inbox UX |
| `GET /health/` | Uptime monitoring |

### Priority 2 — Blocks significant features
| Endpoint | Blocker for |
|----------|-------------|
| `POST /api/candidates/apply/` | Public careers page |
| `GET /api/leave/calendar/` | Leave planner |
| `GET /api/attendance/timesheet/` | Timesheet management |
| `POST /api/push-subscriptions/` | PWA push notifications |
| `GET /api/employees/org-chart/` | Org chart feature |
| `GET /api/payroll/documents/me/` | Employee payslip downloads |

### Priority 3 — Enhances but not blocking
| Endpoint | Feature |
|----------|---------|
| `POST /api/lms/courses/{id}/rate/` | Course ratings |
| `POST /api/candidates/{id}/resume/` | Resume upload |
| `GET /api/performance/team-goals/` | Manager team view |
| `POST /api/auth/password-reset/` | Password recovery |
| `GET /api/manager/summary/` | Manager dashboard KPIs |

---

## Effort Estimate Summary

| Category | Missing endpoints | Estimated dev days |
|----------|------------------|--------------------|
| Auth completeness (logout, refresh, me) | 3 | 1 day |
| Employee self-service gaps | 4 | 2 days |
| Attendance gaps | 2 | 1 day |
| Notification system (unread, read, push) | 4 | 3–5 days (push is complex) |
| Recruitment public apply | 1 | 1 day |
| Leave calendar | 1 | 1 day |
| **Total (P1 + P2)** | **~15 endpoints** | **~10–12 days** |
