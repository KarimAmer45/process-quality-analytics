-- Dashboard counts refer to the latest imported version of each named workbook.
CREATE VIEW lab.v_etl_latest AS
WITH latest AS (
 SELECT DISTINCT ON(file_name) file_name,sha256 FROM lab.import_file
 ORDER BY file_name,applied_at DESC,sha256
)
SELECT s.* FROM lab.v_etl_status s JOIN latest l ON l.sha256=s.import_hash;
CREATE VIEW lab.v_bi_nickel AS
SELECT tank_code,sampled_local,value,mr,cl,ucl,lcl,mr_ucl,beyond_limits,rule4_signal
FROM lab.v_bi_imr WHERE tank_code='L1-T05' AND parameter_code='NI';
CREATE VIEW lab.v_rule4_runs AS
SELECT tank_code,parameter_code,side,grp,min(sampled_at) AS run_start,
 max(sampled_at) AS run_end,count(*) AS observations,
 min(sampled_at) FILTER(WHERE rule4_signal) AS first_signal,
 count(*) FILTER(WHERE rule4_signal) AS signal_count
FROM lab.v_run_rules WHERE side<>0
GROUP BY tank_code,parameter_code,side,grp HAVING bool_or(rule4_signal);
CREATE VIEW lab.v_bi_capability AS SELECT tank_code,parameter_code,month,n,mean,sigma_within,lsl,usl,cpk,interpretation
FROM lab.v_monthly_capability WHERE tank_code='L1-T05';
GRANT SELECT ON ALL TABLES IN SCHEMA lab TO role_readonly,role_lab,role_quality;
