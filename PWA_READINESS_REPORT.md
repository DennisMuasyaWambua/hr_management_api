# PWA Readiness Report

**Date:** 2026-06-24  
**Scope:** API readiness to support a Progressive Web App front-end  
**Context:** The PWA is a separate Next.js repository deployed at `hr-system-dashboard-sheerlogic.vercel.app`. This report assesses how well the API backend supports that client.

---

## Summary

The API was **designed with a PWA client in mind**. OTP-based authentication, identity header propagation, one-tap SMS/WhatsApp links, geofencing with face verification, and CORS configuration for the Vercel domain are all intentionally built. However, several API capabilities are incomplete or missing that a production PWA will require.

**PWA Support Score: 62 / 100**

---

## 1. Authentication & Identity — Score: 75/100

### What's ready
| Feature | Status | Notes |
|---------|--------|-------|
| Email OTP login | ✅ Ready | `SendOTPView` + `VerifyOTPView`; 6-digit, 10-min TTL, 60s resend cooldown |
| Token returned on OTP verify | ✅ Ready | Returns `token`, `user_id`, `role`, `company_id`, `employee_id`, `worker_class` |
| Password login (dashboard) | ✅ Ready | `AuthLoginView` at `api/auth/login/` |
| CORS for Vercel domain | ✅ Ready | `https://hr-system-dashboard-sheerlogic.vercel.app` in `CORS_ALLOWED_ORIGINS` |
| Identity header propagation | ✅ Ready | Next.js route handlers forward `X-User-Id`, `X-User-Role`, `X-Company-Id` |
| Service-key for server-side calls | ✅ Ready | `ServiceKeyAuthentication` (HMAC) |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No token refresh / expiry | HIGH — tokens never expire; stolen tokens persist forever | Medium — add simplejwt |
| No logout endpoint | MEDIUM — tokens can't be invalidated client-side | Low — add token delete view |
| No password reset flow | MEDIUM — no `forgot password` email link | Medium |
| No `GET /api/auth/me/` that also returns company + role | LOW — `MeView` exists but returns minimal data | Low |

---

## 2. Employee Self-Service — Score: 70/100

### What's ready
| Feature | API | Status |
|---------|-----|--------|
| View payslips | `GET /api/payslips/` (MyPayslipsView) | ✅ |
| Apply for leave | `POST /api/leave/` | ✅ |
| View leave balance | `GET /api/leave-balances/` | ✅ |
| Submit overtime | `POST /api/overtime/` | ✅ |
| Submit reimbursement | `POST /api/reimbursements/` | ✅ |
| View announcements | `GET /api/announcements/` | ✅ |
| View own KPIs | `GET /api/kpi-assignments/` | ✅ |
| Enrol in LMS course | `POST /api/lms/enrollments/` | ✅ |
| View own goals | `GET /api/performance/goals/?employee_id=` | ✅ |
| View certificates | `GET /api/certificates/` | ✅ |
| View notifications | `GET /api/notifications/` (NotificationLog) | ✅ |
| Update profile picture | `POST /api/profile-picture/` | ✅ |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No `GET /api/employees/me/` returning own `EmployeeProfile` | HIGH — PWA needs employee's own profile data | Low |
| No payslip PDF download link | HIGH — payslips returned as JSON; PWA needs downloadable PDF | Medium |
| No push notification support (FCM/VAPID) | HIGH — PWA can't push alerts without a push service | High |
| No read/dismiss notifications endpoint | MEDIUM — `NotificationLog` is append-only (no mark-as-read) | Low |
| No document list for employee | MEDIUM — can't list own payroll documents | Low |

---

## 3. Check-In / Attendance (Blue-Collar PWA) — Score: 85/100

This is the most PWA-native feature — designed specifically for the PWA.

### What's ready
| Feature | API | Status |
|---------|-----|--------|
| Geofenced check-in | `POST /api/attendance/check-in/` | ✅ |
| Location ping | `POST /api/attendance/ping/` | ✅ |
| View attendance history | `GET /api/attendance/events/` | ✅ |
| Face verification data stored | `face_verified`, `face_confidence` on `AttendanceEvent` | ✅ |
| source_app='pwa' default | Attribute on `AttendanceEvent` | ✅ |
| Geofence violation tracking | `GeofenceViolation` model + endpoint | ✅ |
| Out-of-zone reason submission | `out_of_zone_reason` field | ✅ |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No `GET /api/attendance/today/` summary for employee | MEDIUM — PWA home screen needs today's check-in status | Low |
| No shift/schedule model | HIGH — PWA can't show "next shift" or enforce shift-based check-in windows | High |
| Offline sync not supported | MEDIUM — no endpoint to batch-upload attendance events recorded offline | Medium |
| Face descriptor stored only on EmployeeProfile | MEDIUM — no server-side face verification; client does face-api.js comparison | Architecture gap |

---

## 4. Approval Workflows — Score: 80/100

### What's ready
| Feature | Status |
|---------|--------|
| One-tap leave approval via SMS link | ✅ `OneTapToken` + `OneTapApprovalView` |
| One-tap overtime approval | ✅ |
| One-tap payroll approval | ✅ |
| Payroll DocuSeal e-signature | ✅ |
| Manager leave approve/reject | ✅ `PATCH /api/leave/{id}/` with status field |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No manager dashboard summary endpoint | HIGH — manager PWA needs "pending items" count per type | Low |
| No bulk approve | MEDIUM — approving 30 leave requests requires 30 API calls | Medium |
| Leave recall notification not tracked | LOW | Low |

---

## 5. Recruitment PWA Features — Score: 55/100

### What's ready
| Feature | Status |
|---------|--------|
| Job postings list | ✅ |
| Candidate pipeline view | ✅ |
| Schedule interview | ✅ |
| Candidate search (10 filters) | ✅ |
| Talent pools | ✅ |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No public job application endpoint | HIGH — candidates can't self-apply (auth required) | Medium |
| No interview calendar/iCal export | MEDIUM | Medium |
| No offer letter generation | HIGH | High |
| Candidate resume upload not in API | HIGH — `resume_url` stored but upload endpoint missing | Medium |

---

## 6. Notifications & Real-Time — Score: 30/100

This is the largest PWA gap.

### What's ready
| Feature | Status |
|---------|--------|
| Email notifications | ✅ (Resend SMTP + EmailJS) |
| SMS notifications | ✅ (Africa's Talking) |
| WhatsApp notifications | ✅ (Africa's Talking Chat API) |
| In-app notification log | ✅ (`NotificationLog` table, readable via API) |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No push notifications (FCM/VAPID) | CRITICAL — PWA without push is just a website | High |
| No WebSocket / Server-Sent Events | HIGH — real-time updates (payroll processing, check-in confirmation) require polling | High |
| No unread count endpoint | HIGH — `GET /api/notifications/unread-count/` | Low |
| No mark-as-read endpoint | HIGH | Low |
| No notification preferences endpoint | MEDIUM — user can't configure which channels to use | Medium |

---

## 7. Analytics / Dashboard — Score: 65/100

### What's ready
| Feature | Status |
|---------|--------|
| Executive overview KPIs | ✅ `GET /api/analytics/overview/` |
| Headcount by dept/type/class | ✅ `GET /api/analytics/headcount/` |
| Payroll trend | ✅ `GET /api/analytics/payroll/` |
| Leave utilisation | ✅ `GET /api/analytics/leave/` |
| Recruitment funnel | ✅ `GET /api/analytics/recruitment/` |
| Placement analytics | ✅ `GET /api/analytics/placements/` |
| Workforce analytics | ✅ `GET /api/analytics/workforce/` (hr app) |

### Gaps
| Gap | Impact | Effort |
|-----|--------|--------|
| No employee-level analytics | HIGH — PWA can't show "your attendance rate" or "your payslip trend" | Medium |
| Analytics not scoped to employee role | MEDIUM — all analytics are HR-only; employees see nothing | Low |
| No real-time dashboard (WebSocket) | MEDIUM | High |
| Cache TTL 300s may feel stale | LOW — dashboards may lag 5 minutes | Low |

---

## 8. Offline Support Readiness — Score: 20/100

| Feature | Status |
|---------|--------|
| API supports `If-None-Match` / ETag | ❌ Not implemented |
| Structured responses (stable shape) | ✅ DRF serializers ensure consistent shape |
| Batch API (multiple operations) | ❌ No batch endpoint |
| Offline attendance sync | ❌ No bulk event upload |
| Conflict resolution headers | ❌ No `Last-Modified` or optimistic locking |

---

## 9. PWA-Required Endpoints Missing

These endpoints don't exist and would be among the first things a PWA integration would hit:

| Endpoint | Purpose | Priority |
|----------|---------|---------|
| `GET /api/employees/me/` | Employee's own full profile | P1 |
| `GET /api/attendance/today/` | Today's check-in status | P1 |
| `POST /api/auth/logout/` | Invalidate token | P1 |
| `GET /api/notifications/unread-count/` | Badge count | P1 |
| `POST /api/notifications/{id}/read/` | Mark as read | P1 |
| `GET /health/` | Uptime check | P1 |
| `POST /api/attendance/events/bulk/` | Offline sync batch upload | P2 |
| `GET /api/payroll/documents/me/` | Employee's own payslip PDFs | P2 |
| `POST /api/candidates/apply/` | Public job application | P2 |
| `GET /api/manager/pending-actions/` | Manager action queue | P2 |
| `POST /api/push-subscriptions/` | Store FCM/VAPID subscription | P3 |

---

## 10. CORS Configuration

Current `CORS_ALLOWED_ORIGINS` covers:
- `http://localhost:3000`, `http://localhost:3001`, `http://localhost:3002`
- `http://127.0.0.1:3000`
- `https://hr-system-dashboard-sheerlogic.vercel.app`

**Gap:** Vercel preview deployments use dynamic URLs (`https://hr-dashboard-xyz-sheerlogic.vercel.app`). These are currently blocked by CORS.

**Fix:** Add `CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://hr-system-dashboard.*\.vercel\.app$"]` for preview environments.

---

## Recommended PWA Priority Order

1. **Add token refresh / logout** (auth security)
2. **Add `GET /api/employees/me/`** (every screen needs this)
3. **Add `GET /api/attendance/today/`** (blue-collar home screen)
4. **Add notification unread count + mark-read** (engagement)
5. **Add push notification support (FCM)** (PWA killer feature)
6. **Add offline attendance batch upload** (blue-collar reliability)
7. **Add public job application endpoint** (recruitment funnel)
