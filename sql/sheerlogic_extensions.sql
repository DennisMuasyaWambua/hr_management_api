-- ============================================================================
-- Sheer Logic extensions — Supabase mirror of the new Django-managed tables
-- (01 June 2026 session features). Run in the Supabase SQL editor AFTER the
-- Django API is deployed against this database, OR use it to create the
-- tables Supabase-side if you prefer Supabase as the single Postgres.
--
-- If Django `migrate` already created these tables in this database, skip the
-- CREATE TABLE section and apply only the RLS section at the bottom.
-- ============================================================================

-- ---- RBAC ------------------------------------------------------------------
create table if not exists rbac_roles (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id),
  tenant_id uuid,
  slug varchar(50) not null,
  name varchar(100) not null,
  rank integer not null default 100,
  is_system boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, slug)
);

create table if not exists rbac_permissions (
  id uuid primary key default gen_random_uuid(),
  codename varchar(100) not null unique,
  module varchar(50) not null,
  description text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists rbac_role_permissions (
  id uuid primary key default gen_random_uuid(),
  role_id uuid not null references rbac_roles(id) on delete cascade,
  permission_id uuid not null references rbac_permissions(id) on delete cascade,
  granted_by uuid,
  created_at timestamptz not null default now(),
  unique (role_id, permission_id)
);

create table if not exists rbac_user_roles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  company_id uuid,
  tenant_id uuid,
  role_id uuid not null references rbac_roles(id) on delete cascade,
  assigned_by uuid,
  created_at timestamptz not null default now(),
  unique (user_id, company_id, role_id)
);

-- ---- Audit & notifications ---------------------------------------------------
create table if not exists service_audit_log (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  actor_user_id uuid, actor_label varchar(255) not null default '',
  action varchar(100) not null,
  object_type varchar(100) not null default '',
  object_id varchar(100) not null default '',
  metadata jsonb not null default '{}',
  ip_address inet
);
create index if not exists idx_audit_action on service_audit_log(action, created_at desc);

create table if not exists notification_templates (
  id uuid primary key default gen_random_uuid(),
  company_id uuid, event varchar(100) not null, channel varchar(10) not null,
  subject varchar(255) not null default '', body text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, event, channel)
);

create table if not exists notification_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  source_app varchar(20) not null default '',
  event varchar(100) not null default '',
  channel varchar(10) not null, recipient varchar(255) not null,
  subject varchar(255) not null default '', body text not null default '',
  status varchar(10) not null default 'queued',
  attempts integer not null default 0,
  provider_message_id varchar(255) not null default '',
  error text not null default '',
  related_object_type varchar(100) not null default '',
  related_object_id varchar(100) not null default ''
);

create table if not exists one_tap_tokens (
  id uuid primary key default gen_random_uuid(),
  token varchar(64) not null unique,
  action varchar(50) not null,
  object_id varchar(100) not null,
  approver_user_id uuid not null,
  company_id uuid, tenant_id uuid,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);

-- ---- Payroll approvals & documents --------------------------------------------
create table if not exists payroll_approver_configs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  tenant_id uuid,
  company_id uuid not null unique references companies(id),
  required_approvals integer not null default 2,
  is_active boolean not null default true
);

create table if not exists payroll_approvers (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  config_id uuid not null references payroll_approver_configs(id) on delete cascade,
  user_id uuid not null,
  name varchar(255) not null default '',
  email varchar(254) not null,
  phone varchar(20) not null default '',
  "order" integer not null default 0,
  is_active boolean not null default true,
  unique (config_id, user_id)
);

create table if not exists payroll_approvals (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  payroll_run_id uuid not null references payroll_runs(id),
  approver_user_id uuid not null,
  decision varchar(10) not null,
  via varchar(10) not null default 'dashboard',
  comment text not null default '',
  docuseal_submitter_slug varchar(100) not null default '',
  ip_address inet,
  signed_at timestamptz not null default now(),
  unique (payroll_run_id, approver_user_id)
);

create table if not exists payroll_documents (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  payroll_run_id uuid not null references payroll_runs(id),
  payroll_record_id uuid,
  doc_type varchar(20) not null,
  file varchar(255) not null,
  sha256 varchar(64) not null,
  password_protected boolean not null default false,
  docuseal_template_id varchar(100) not null default '',
  docuseal_submission_id varchar(100) not null default '',
  is_signed boolean not null default false,
  is_locked boolean not null default false,
  generated_by uuid
);

-- Payroll runs gain two additive statuses (no schema change needed; status is
-- text). Document for CHECK-constraint users:
--   draft → calculated → pending_approval → approved → processing → completed/paid

-- ---- HR: allowances/deductions/overtime/reimbursements -------------------------
create table if not exists allowance_types (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid references companies(id),
  name varchar(100) not null, taxable boolean not null default true,
  is_variable boolean not null default false,
  default_amount numeric(12,2) not null default 0,
  is_active boolean not null default true,
  unique (company_id, name)
);

create table if not exists employee_allowances (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  allowance_type_id uuid not null references allowance_types(id) on delete cascade,
  amount numeric(12,2) not null,
  effective_from date not null default current_date,
  effective_to date,
  is_active boolean not null default true,
  created_by uuid
);

create table if not exists deduction_types (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid references companies(id),
  name varchar(100) not null, is_active boolean not null default true,
  unique (company_id, name)
);

create table if not exists disciplinary_records (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  kind varchar(30) not null, status varchar(15) not null default 'open',
  title varchar(255) not null, description text not null default '',
  document_url text not null default '', issued_by uuid,
  starts_on date, ends_on date, outcome text not null default '',
  escalated_from_id uuid references disciplinary_records(id)
);

create table if not exists employee_deductions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  deduction_type_id uuid not null references deduction_types(id) on delete cascade,
  amount numeric(12,2) not null,
  effective_from date not null default current_date,
  effective_to date,
  is_active boolean not null default true,
  disciplinary_record_id uuid references disciplinary_records(id),
  created_by uuid
);

create table if not exists overtime_requests (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  manager_id uuid,
  date date not null, hours numeric(5,2) not null,
  rate_multiplier numeric(4,2) not null default 1.5,
  reason text not null default '',
  status varchar(10) not null default 'pending',
  decided_by uuid, decided_at timestamptz
);

create table if not exists reimbursements (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  category varchar(100) not null, amount numeric(12,2) not null,
  description text not null default '', receipt_url text not null default '',
  status varchar(10) not null default 'submitted',
  processed_by uuid, processed_at timestamptz,
  payment_reference varchar(255) not null default ''
);

-- ---- Statutory rates, minimum wage, compliance ----------------------------------
create table if not exists statutory_rates (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid references companies(id),
  kind varchar(20) not null, value jsonb not null,
  effective_from date not null, effective_to date,
  note varchar(255) not null default '', created_by uuid
);

create table if not exists minimum_wages (
  id uuid primary key default gen_random_uuid(),
  job_category varchar(150) not null, region varchar(100) not null default 'general',
  monthly_amount numeric(12,2) not null, effective_from date not null,
  source varchar(255) not null default '',
  created_at timestamptz not null default now()
);

create table if not exists compliance_alerts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  alert_type varchar(30) not null,
  employee_id uuid references employee_profiles(id),
  payroll_run_id uuid,
  details jsonb not null default '{}',
  status varchar(15) not null default 'open',
  acknowledged_by uuid
);

-- ---- Exits & clearance ------------------------------------------------------------
create table if not exists employee_exits (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  kind varchar(20) not null, status varchar(15) not null default 'initiated',
  reason text not null default '',
  notice_date date, last_working_day date, initiated_by uuid,
  disciplinary_record_id uuid references disciplinary_records(id),
  final_dues jsonb not null default '{}',
  final_dues_total numeric(14,2),
  final_dues_paid_at timestamptz,
  final_payroll_record_id uuid
);

create table if not exists exit_clearance_items (
  id uuid primary key default gen_random_uuid(),
  exit_id uuid not null references employee_exits(id) on delete cascade,
  item varchar(255) not null,
  is_cleared boolean not null default false,
  cleared_by uuid, cleared_at timestamptz,
  notes text not null default ''
);

-- ---- Leave recall & certificates -----------------------------------------------------
create table if not exists leave_recalls (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  leave_id uuid not null references leaves(id),
  employee_id uuid not null references employee_profiles(id),
  manager_id uuid, requested_by uuid,
  reason text not null default '', resume_date date not null,
  days_credited numeric(5,1),
  status varchar(10) not null default 'pending',
  decided_by uuid, decided_at timestamptz
);

create table if not exists employee_certificates (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid,
  employee_id uuid not null references employee_profiles(id),
  name varchar(255) not null, issuer varchar(255) not null default '',
  certificate_number varchar(100) not null default '',
  issue_date date, expiry_date date,
  document_url text not null default '',
  alert_days_before integer not null default 30,
  last_alert_sent_at timestamptz,
  is_active boolean not null default true
);
create index if not exists idx_certificates_expiry on employee_certificates(expiry_date);

-- ---- Geofencing (work zones live wherever Django default DB is; mirror here
--      only if the dashboard reads them via Supabase) --------------------------------
create table if not exists work_zones (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid not null references companies(id),
  name varchar(255) not null,
  center_lat double precision not null, center_lng double precision not null,
  radius_m integer not null default 200,
  work_start time not null default '08:00', work_end time not null default '17:00',
  is_active boolean not null default true
);

create table if not exists geofence_violations (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  tenant_id uuid, company_id uuid not null,
  employee_id uuid not null,
  zone_id uuid references work_zones(id),
  started_at timestamptz not null, ended_at timestamptz,
  distance_m double precision, reason text not null default '',
  status varchar(20) not null default 'open',
  reviewed_by uuid
);

-- NOTE: attendance_events intentionally NOT mirrored here — it lives in the
-- dedicated TimescaleDB instance (hypertable) and is queried through the
-- Django API only.

-- ============================================================================
-- RLS — service-role full access; authenticated users scoped by company.
-- Payroll tables: HR/admin roles ONLY (mirrors PayrollHROnly). Geofence
-- violations: HQ roles only, NEVER the employee (01-Jun rule).
-- Assumes public.users has (id uuid, company_id uuid, role text).
-- ============================================================================
do $$
declare t text;
begin
  foreach t in array array[
    'rbac_roles','rbac_permissions','rbac_role_permissions','rbac_user_roles',
    'service_audit_log','notification_templates','notification_logs','one_tap_tokens',
    'payroll_approver_configs','payroll_approvers','payroll_approvals','payroll_documents',
    'allowance_types','employee_allowances','deduction_types','employee_deductions',
    'overtime_requests','reimbursements','statutory_rates','minimum_wages',
    'compliance_alerts','disciplinary_records','employee_exits','exit_clearance_items',
    'leave_recalls','employee_certificates','work_zones','geofence_violations']
  loop
    execute format('alter table %I enable row level security', t);
    execute format($f$create policy svc_all_%1$s on %1$I
                   for all to service_role using (true) with check (true)$f$, t);
  end loop;
end $$;

-- HR/admin-only payroll visibility
create policy hr_read_payroll_documents on payroll_documents for select to authenticated
  using (exists (select 1 from users u where u.id = auth.uid()
                 and u.company_id = payroll_documents.company_id
                 and u.role in ('super_admin','company_admin','hr')));

create policy hr_read_payroll_approvals on payroll_approvals for select to authenticated
  using (exists (select 1 from users u where u.id = auth.uid()
                 and u.company_id = payroll_approvals.company_id
                 and u.role in ('super_admin','company_admin','hr')));

-- Geofence violations: HQ dashboard only, never employees
create policy hq_read_geofence on geofence_violations for select to authenticated
  using (exists (select 1 from users u where u.id = auth.uid()
                 and u.company_id = geofence_violations.company_id
                 and u.role in ('super_admin','company_admin','hr')));

-- Employees can read their own allowances/certificates/reimbursements/overtime
create policy own_rows_allowances on employee_allowances for select to authenticated
  using (employee_id in (select ep.id from employee_profiles ep where ep.user_id = auth.uid()));
create policy own_rows_certificates on employee_certificates for select to authenticated
  using (employee_id in (select ep.id from employee_profiles ep where ep.user_id = auth.uid()));
create policy own_rows_reimbursements on reimbursements for all to authenticated
  using (employee_id in (select ep.id from employee_profiles ep where ep.user_id = auth.uid()))
  with check (employee_id in (select ep.id from employee_profiles ep where ep.user_id = auth.uid()));
create policy own_rows_overtime on overtime_requests for select to authenticated
  using (employee_id in (select ep.id from employee_profiles ep where ep.user_id = auth.uid())
         or manager_id = auth.uid());
