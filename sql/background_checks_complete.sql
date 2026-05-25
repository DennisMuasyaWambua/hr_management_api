-- ─────────────────────────────────────────────────────────────
-- MIGRATION: Complete Background Checks Module
-- Run this in Supabase SQL Editor to add missing components
-- URL: https://supabase.com/dashboard/project/mcbbtrrhqweypfnlzwht/sql/new
-- ─────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────
-- 1. ADD CHECK CONSTRAINT (employee_id OR candidate_id required)
-- ─────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_has_subject'
  ) THEN
    ALTER TABLE background_checks
    ADD CONSTRAINT check_has_subject CHECK (
      (employee_id IS NOT NULL) OR (candidate_id IS NOT NULL)
    );
  END IF;
END $$;

-- ─────────────────────────────────────────────────────────────
-- 2. CREATE INDEXES FOR PERFORMANCE
-- ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_background_checks_employee
  ON background_checks(employee_id)
  WHERE employee_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_background_checks_candidate
  ON background_checks(candidate_id)
  WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_background_checks_company
  ON background_checks(company_id);

CREATE INDEX IF NOT EXISTS idx_background_checks_status
  ON background_checks(status);

CREATE INDEX IF NOT EXISTS idx_background_checks_type
  ON background_checks(check_type);

CREATE INDEX IF NOT EXISTS idx_background_checks_expiry
  ON background_checks(expiry_date)
  WHERE expiry_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_background_checks_tenant
  ON background_checks(tenant_id);

-- ─────────────────────────────────────────────────────────────
-- 3. CREATE OR REPLACE UPDATED_AT TRIGGER FUNCTION
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────
-- 4. ATTACH TRIGGER TO BACKGROUND_CHECKS TABLE
-- ─────────────────────────────────────────────────────────────

DROP TRIGGER IF EXISTS set_updated_at ON background_checks;

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON background_checks
  FOR EACH ROW
  EXECUTE FUNCTION trigger_set_updated_at();

-- ─────────────────────────────────────────────────────────────
-- 5. ENABLE ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────

ALTER TABLE background_checks ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────
-- 6. HELPER FUNCTIONS FOR RLS POLICIES
-- ─────────────────────────────────────────────────────────────

-- These functions already exist in your database and are used by RLS policies.
-- Only create them if they don't exist.

DO $$
BEGIN
  -- current_user_role
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'current_user_role') THEN
    CREATE FUNCTION current_user_role()
    RETURNS TEXT AS $fn$
    BEGIN
      RETURN COALESCE(
        current_setting('request.jwt.claims', true)::json->>'role',
        (SELECT role::text FROM users WHERE id = auth.uid())
      );
    END;
    $fn$ LANGUAGE plpgsql SECURITY DEFINER STABLE;
  END IF;

  -- current_user_company_id
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'current_user_company_id') THEN
    CREATE FUNCTION current_user_company_id()
    RETURNS UUID AS $fn$
    BEGIN
      RETURN COALESCE(
        (current_setting('request.jwt.claims', true)::json->>'company_id')::uuid,
        (SELECT company_id FROM users WHERE id = auth.uid())
      );
    END;
    $fn$ LANGUAGE plpgsql SECURITY DEFINER STABLE;
  END IF;

  -- current_employee_id
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'current_employee_id') THEN
    CREATE FUNCTION current_employee_id()
    RETURNS UUID AS $fn$
    BEGIN
      RETURN (SELECT id FROM employee_profiles WHERE user_id = auth.uid() LIMIT 1);
    END;
    $fn$ LANGUAGE plpgsql SECURITY DEFINER STABLE;
  END IF;
END $$;

-- ─────────────────────────────────────────────────────────────
-- 7. ROW LEVEL SECURITY POLICIES
-- ─────────────────────────────────────────────────────────────

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "bg_checks_super_admin" ON background_checks;
DROP POLICY IF EXISTS "bg_checks_hr_admin" ON background_checks;
DROP POLICY IF EXISTS "bg_checks_manager_read" ON background_checks;
DROP POLICY IF EXISTS "bg_checks_employee_own" ON background_checks;

-- Super admin: full access to all records
CREATE POLICY "bg_checks_super_admin" ON background_checks
  FOR ALL
  USING (current_user_role() = 'super_admin');

-- HR admin: full access within their company
CREATE POLICY "bg_checks_hr_admin" ON background_checks
  FOR ALL
  USING (
    current_user_role() = 'hr_admin' AND
    company_id = current_user_company_id()
  );

-- Manager: read-only within their company
CREATE POLICY "bg_checks_manager_read" ON background_checks
  FOR SELECT
  USING (
    current_user_role() = 'manager' AND
    company_id = current_user_company_id()
  );

-- Employee: read-only for their own checks
CREATE POLICY "bg_checks_employee_own" ON background_checks
  FOR SELECT
  USING (
    employee_id = current_employee_id()
  );

-- ─────────────────────────────────────────────────────────────
-- 8. CAN_HIRE_CANDIDATE FUNCTION
-- ─────────────────────────────────────────────────────────────

-- This function can be safely replaced as it has no dependencies
CREATE OR REPLACE FUNCTION can_hire_candidate(p_candidate_id UUID)
RETURNS JSONB AS $$
DECLARE
  v_company_id UUID;
  v_requires_check BOOLEAN;
  v_blocks_hiring BOOLEAN;
  v_has_passed_check BOOLEAN;
  v_pending_checks INT;
BEGIN
  -- Get company settings for this candidate's job posting
  SELECT
    jp.company_id,
    COALESCE(c.background_check_required, FALSE),
    COALESCE(c.background_check_blocks_hiring, FALSE)
  INTO v_company_id, v_requires_check, v_blocks_hiring
  FROM candidates cand
  JOIN job_postings jp ON jp.id = cand.job_posting_id
  JOIN companies c ON c.id = jp.company_id
  WHERE cand.id = p_candidate_id;

  -- If background check not required, can hire immediately
  IF NOT v_requires_check THEN
    RETURN jsonb_build_object(
      'can_hire', TRUE,
      'reason', 'background_check_not_required'
    );
  END IF;

  -- Check if candidate has a passed background check
  SELECT EXISTS (
    SELECT 1 FROM background_checks
    WHERE candidate_id = p_candidate_id
      AND status = 'passed'
      AND is_deleted = FALSE
  ) INTO v_has_passed_check;

  -- Count pending/in-progress checks
  SELECT COUNT(*) INTO v_pending_checks
  FROM background_checks
  WHERE candidate_id = p_candidate_id
    AND status IN ('pending', 'in_progress')
    AND is_deleted = FALSE;

  -- If has passed check, can hire
  IF v_has_passed_check THEN
    RETURN jsonb_build_object(
      'can_hire', TRUE,
      'reason', 'background_check_passed'
    );
  END IF;

  -- If background check blocks hiring and no passed check
  IF v_blocks_hiring THEN
    RETURN jsonb_build_object(
      'can_hire', FALSE,
      'reason', 'background_check_required',
      'pending_checks', v_pending_checks
    );
  END IF;

  -- Background check required but doesn't block - return warning
  RETURN jsonb_build_object(
    'can_hire', TRUE,
    'warning', TRUE,
    'reason', 'background_check_incomplete',
    'pending_checks', v_pending_checks
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ─────────────────────────────────────────────────────────────
-- 9. GRANT PERMISSIONS
-- ─────────────────────────────────────────────────────────────

GRANT EXECUTE ON FUNCTION can_hire_candidate(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION current_user_role() TO authenticated;
GRANT EXECUTE ON FUNCTION current_user_company_id() TO authenticated;
GRANT EXECUTE ON FUNCTION current_employee_id() TO authenticated;

-- ─────────────────────────────────────────────────────────────
-- VERIFICATION QUERIES (run after migration)
-- ─────────────────────────────────────────────────────────────

-- Verify constraint exists:
-- SELECT conname FROM pg_constraint WHERE conname = 'check_has_subject';

-- Verify indexes exist:
-- SELECT indexname FROM pg_indexes WHERE tablename = 'background_checks';

-- Verify RLS is enabled:
-- SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'background_checks';

-- Verify function exists:
-- SELECT proname FROM pg_proc WHERE proname = 'can_hire_candidate';

-- Test the function (replace with actual candidate_id):
-- SELECT can_hire_candidate('your-candidate-uuid-here');
