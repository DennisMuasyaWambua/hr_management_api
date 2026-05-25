-- ─────────────────────────────────────────────────────────────
-- MIGRATION: Payroll Extensions for Django Integration
-- Run this in Supabase SQL Editor to add payment config columns
-- URL: https://supabase.com/dashboard/project/mcbbtrrhqweypfnlzwht/sql/new
-- ─────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────
-- 1. ADD PAYMENT CONFIG COLUMNS TO COMPANIES TABLE
-- ─────────────────────────────────────────────────────────────

-- Company bank details
ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  company_bank_name TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  company_bank_account TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  company_bank_branch TEXT;

-- M-Pesa details
ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  mpesa_paybill_number TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  mpesa_till_number TEXT;

-- PesaPal integration
ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  pesapal_consumer_key TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  pesapal_consumer_secret TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  pesapal_ipn_id TEXT;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS
  pesapal_sandbox BOOLEAN NOT NULL DEFAULT TRUE;

-- ─────────────────────────────────────────────────────────────
-- 2. CREATE PAYMENT_BATCHES TABLE
-- ─────────────────────────────────────────────────────────────

CREATE TYPE IF NOT EXISTS payment_batch_status AS ENUM (
  'pending',
  'processing',
  'completed',
  'partial',
  'failed'
);

CREATE TABLE IF NOT EXISTS payment_batches (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tenant_id                   UUID NOT NULL,
  payroll_run_id              UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
  payment_method              TEXT NOT NULL CHECK (payment_method IN ('bank', 'mpesa', 'airtel')),
  status                      payment_batch_status NOT NULL DEFAULT 'pending',
  total_amount                NUMERIC NOT NULL,
  successful_amount           NUMERIC NOT NULL DEFAULT 0,
  failed_amount               NUMERIC NOT NULL DEFAULT 0,
  record_count                INTEGER NOT NULL DEFAULT 0,
  successful_count            INTEGER NOT NULL DEFAULT 0,
  failed_count                INTEGER NOT NULL DEFAULT 0,
  pesapal_order_tracking_id   TEXT,
  pesapal_merchant_reference  TEXT,
  started_at                  TIMESTAMPTZ,
  completed_at                TIMESTAMPTZ
);

-- Indexes for payment_batches
CREATE INDEX IF NOT EXISTS idx_payment_batches_payroll_run
  ON payment_batches(payroll_run_id);

CREATE INDEX IF NOT EXISTS idx_payment_batches_status
  ON payment_batches(status);

CREATE INDEX IF NOT EXISTS idx_payment_batches_tenant
  ON payment_batches(tenant_id);

-- Auto-update timestamp trigger
DROP TRIGGER IF EXISTS set_updated_at ON payment_batches;
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON payment_batches
  FOR EACH ROW
  EXECUTE FUNCTION trigger_set_updated_at();

-- ─────────────────────────────────────────────────────────────
-- 3. ROW LEVEL SECURITY FOR PAYMENT_BATCHES
-- ─────────────────────────────────────────────────────────────

ALTER TABLE payment_batches ENABLE ROW LEVEL SECURITY;

-- Super admin: full access
CREATE POLICY "payment_batches_super_admin" ON payment_batches
  FOR ALL
  USING (current_user_role() = 'super_admin');

-- HR admin: full access within their company
CREATE POLICY "payment_batches_hr_admin" ON payment_batches
  FOR ALL
  USING (
    current_user_role() = 'hr_admin' AND
    payroll_run_id IN (
      SELECT id FROM payroll_runs WHERE company_id = current_user_company_id()
    )
  );

-- Manager: read-only within their company
CREATE POLICY "payment_batches_manager_read" ON payment_batches
  FOR SELECT
  USING (
    current_user_role() = 'manager' AND
    payroll_run_id IN (
      SELECT id FROM payroll_runs WHERE company_id = current_user_company_id()
    )
  );

-- ─────────────────────────────────────────────────────────────
-- 4. ADDITIONAL INDEXES FOR PAYROLL PERFORMANCE
-- ─────────────────────────────────────────────────────────────

-- Payroll runs indexes
CREATE INDEX IF NOT EXISTS idx_payroll_runs_company
  ON payroll_runs(company_id);

CREATE INDEX IF NOT EXISTS idx_payroll_runs_period
  ON payroll_runs(period_year, period_month);

CREATE INDEX IF NOT EXISTS idx_payroll_runs_status
  ON payroll_runs(status);

-- Payroll records indexes
CREATE INDEX IF NOT EXISTS idx_payroll_records_run
  ON payroll_records(payroll_run_id);

CREATE INDEX IF NOT EXISTS idx_payroll_records_employee
  ON payroll_records(employee_id);

CREATE INDEX IF NOT EXISTS idx_payroll_records_status
  ON payroll_records(payment_status);

-- ─────────────────────────────────────────────────────────────
-- 5. HELPER FUNCTION: Calculate payroll totals
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_payroll_run_totals(p_payroll_run_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE payroll_runs
  SET
    total_gross = COALESCE((
      SELECT SUM(gross_salary)
      FROM payroll_records
      WHERE payroll_run_id = p_payroll_run_id AND is_deleted = FALSE
    ), 0),
    total_deductions = COALESCE((
      SELECT SUM(paye + nssf + nhif + helb + other_deductions)
      FROM payroll_records
      WHERE payroll_run_id = p_payroll_run_id AND is_deleted = FALSE
    ), 0),
    total_net = COALESCE((
      SELECT SUM(net_salary)
      FROM payroll_records
      WHERE payroll_run_id = p_payroll_run_id AND is_deleted = FALSE
    ), 0),
    updated_at = NOW()
  WHERE id = p_payroll_run_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION update_payroll_run_totals(UUID) TO authenticated;

-- ─────────────────────────────────────────────────────────────
-- VERIFICATION QUERIES
-- ─────────────────────────────────────────────────────────────

-- Check new columns exist:
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'companies' AND column_name LIKE 'pesapal%';

-- Check payment_batches table:
-- SELECT * FROM payment_batches LIMIT 1;

-- Check indexes:
-- SELECT indexname FROM pg_indexes WHERE tablename = 'payment_batches';
