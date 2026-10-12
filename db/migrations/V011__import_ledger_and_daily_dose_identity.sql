-- Import ledger write protection (finding F-07) and day-level identity for daily dose totals (F-03).

-- 1. lab.import_file and lab.stg_excel_row are insert-only for application roles. The ETL only
--    inserts into them. Only the table owner or a superuser can still change or delete ledger rows
--    (for example to remove personal data), and every such change is written to audit.change_log.
CREATE OR REPLACE FUNCTION lab.guard_import_ledger() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, lab AS $$
BEGIN
  IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)
     OR pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = TG_RELID), 'USAGE') THEN
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  RAISE EXCEPTION 'The import ledger (%.%) is insert-only; % is not allowed', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP;
END $$;
REVOKE ALL ON FUNCTION lab.guard_import_ledger() FROM PUBLIC;

DROP TRIGGER IF EXISTS import_file_guard ON lab.import_file;
CREATE TRIGGER import_file_guard BEFORE UPDATE OR DELETE ON lab.import_file
  FOR EACH ROW EXECUTE FUNCTION lab.guard_import_ledger();
DROP TRIGGER IF EXISTS import_file_truncate_guard ON lab.import_file;
CREATE TRIGGER import_file_truncate_guard BEFORE TRUNCATE ON lab.import_file
  FOR EACH STATEMENT EXECUTE FUNCTION lab.guard_import_ledger();
DROP TRIGGER IF EXISTS stg_excel_row_guard ON lab.stg_excel_row;
CREATE TRIGGER stg_excel_row_guard BEFORE UPDATE OR DELETE ON lab.stg_excel_row
  FOR EACH ROW EXECUTE FUNCTION lab.guard_import_ledger();
DROP TRIGGER IF EXISTS stg_excel_row_truncate_guard ON lab.stg_excel_row;
CREATE TRIGGER stg_excel_row_truncate_guard BEFORE TRUNCATE ON lab.stg_excel_row
  FOR EACH STATEMENT EXECUTE FUNCTION lab.guard_import_ledger();

-- Inserts are already described by the import report; the remaining change path is audited.
-- TRUNCATE has no row triggers, so a statement trigger logs every row it is about to remove as a
-- DELETE (the audit log only knows INSERT/UPDATE/DELETE). It runs for the owner or a superuser;
-- for everyone else TRUNCATE is revoked, and the guard above refuses it.
CREATE OR REPLACE FUNCTION lab.audit_ledger_truncate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, lab, audit AS $$
DECLARE pk text;
BEGIN
  IF TG_TABLE_SCHEMA <> 'lab' OR TG_TABLE_NAME NOT IN ('import_file','stg_excel_row') OR TG_OP <> 'TRUNCATE' THEN
    RAISE EXCEPTION 'lab.audit_ledger_truncate() may only run as the TRUNCATE trigger of the import ledger';
  END IF;
  SELECT 'jsonb_build_object(' || string_agg(format('%L,t.%I', a, a), ',') || ')' INTO pk
    FROM unnest(TG_ARGV) a;
  EXECUTE format('INSERT INTO audit.change_log(table_name,operation,row_pk,old_row) '
              || 'SELECT %L,''DELETE'',%s,to_jsonb(t) FROM %I.%I t',
                 TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, pk, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION lab.audit_ledger_truncate() FROM PUBLIC;
DROP TRIGGER IF EXISTS import_file_truncate_audit ON lab.import_file;
CREATE TRIGGER import_file_truncate_audit BEFORE TRUNCATE ON lab.import_file
  FOR EACH STATEMENT EXECUTE FUNCTION lab.audit_ledger_truncate('sha256');
DROP TRIGGER IF EXISTS stg_excel_row_truncate_audit ON lab.stg_excel_row;
CREATE TRIGGER stg_excel_row_truncate_audit BEFORE TRUNCATE ON lab.stg_excel_row
  FOR EACH STATEMENT EXECUTE FUNCTION lab.audit_ledger_truncate('import_hash', 'sheet_name', 'row_no');

DROP TRIGGER IF EXISTS import_file_audit ON lab.import_file;
CREATE TRIGGER import_file_audit AFTER UPDATE OR DELETE ON lab.import_file
  FOR EACH ROW EXECUTE FUNCTION audit.log_change('sha256');
DROP TRIGGER IF EXISTS stg_excel_row_audit ON lab.stg_excel_row;
CREATE TRIGGER stg_excel_row_audit AFTER UPDATE OR DELETE ON lab.stg_excel_row
  FOR EACH ROW EXECUTE FUNCTION audit.log_change('import_hash', 'sheet_name', 'row_no');

REVOKE UPDATE, DELETE, TRUNCATE ON lab.import_file, lab.stg_excel_row
  FROM role_lab, role_ingest, role_operator, role_quality;

-- 2. A daily-total dose is identified by tank | Berlin date | additive. Earlier imports keyed it by
--    the full timestamp, so a corrected time became a second dose. Rewrite existing imported keys
--    (audited by dosing_audit); refuse if two stored doses would collapse into one daily total.
--    to_char keeps the key format independent of the session's DateStyle.
DO $$
DECLARE clash text;
BEGIN
  SELECT string_agg(k, ', ') INTO clash FROM (
    SELECT t.code || '|' || to_char(d.dosed_at AT TIME ZONE 'Europe/Berlin', 'YYYY-MM-DD') || '|' || d.additive AS k
      FROM lab.dosing d JOIN ref.tank t USING (tank_id)
     WHERE d.event_key IS NOT NULL
     GROUP BY 1 HAVING count(*) > 1) x;
  IF clash IS NOT NULL THEN
    RAISE EXCEPTION 'Several stored doses share one daily-total key; review them before migrating: %', clash;
  END IF;
  UPDATE lab.dosing d
     SET event_key = t.code || '|' || to_char(d.dosed_at AT TIME ZONE 'Europe/Berlin', 'YYYY-MM-DD') || '|' || d.additive
    FROM ref.tank t
   WHERE t.tank_id = d.tank_id AND d.event_key IS NOT NULL
     AND d.event_key IS DISTINCT FROM t.code || '|' || to_char(d.dosed_at AT TIME ZONE 'Europe/Berlin', 'YYYY-MM-DD') || '|' || d.additive;
END $$;
