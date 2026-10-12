GRANT USAGE ON SCHEMA ref,lab,trace,realdata TO role_readonly,role_lab,role_quality,role_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA ref,lab,trace,realdata TO role_readonly,role_lab,role_quality,role_ingest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ref,lab,trace,realdata TO role_lab,role_quality,role_ingest;
GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA ref,lab,trace,realdata TO role_ingest;
GRANT INSERT ON lab.analysis,lab.import_file,lab.stg_excel_row TO role_lab;
GRANT INSERT,UPDATE ON lab.analysis_result,lab.dosing,lab.hull_cell TO role_lab;
GRANT INSERT,UPDATE ON lab.parameter_limit,lab.spc_baseline TO role_quality;
GRANT USAGE ON SCHEMA audit TO role_quality;
GRANT SELECT ON audit.change_log TO role_quality;
-- Evidence and ledger tables: the broad grants above must not reopen these change paths.
REVOKE UPDATE, DELETE, TRUNCATE ON lab.analysis FROM role_lab, role_ingest, role_operator, role_quality;
REVOKE DELETE, TRUNCATE ON lab.parameter_limit FROM role_quality, role_ingest;
REVOKE UPDATE, DELETE, TRUNCATE ON lab.import_file, lab.stg_excel_row FROM role_lab, role_ingest, role_operator, role_quality;
