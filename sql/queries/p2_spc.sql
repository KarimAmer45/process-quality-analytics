-- A: rule 4, including first signal and the full run (eight points minimum).
SELECT * FROM lab.v_rule4_runs ORDER BY parameter_code,run_start;
-- B: monthly Cpk and Ppk, split whenever specification versions change, labelled by the month's signals.
SELECT * FROM lab.v_monthly_capability ORDER BY tank_code,parameter_code,month;
-- Baseline status: are the chart limits usable, and on how many Phase I points?
SELECT * FROM lab.v_spc_status ORDER BY tank_code,parameter_code;
-- C: published NIST answers reproduced directly in PostgreSQL.
SELECT * FROM realdata.v_nist_summary;
SELECT * FROM realdata.v_nist_anova;
-- D: retrospective SECOM comparisons; no imputation, no predictive claims.
SELECT * FROM realdata.v_secom_ranking WHERE effect_size IS NOT NULL
ORDER BY abs(effect_size) DESC,feature_no LIMIT 20;
-- E: daily consumption normalized by simulated physical charge.
SELECT additive,count(*) AS days,min(ml_per_kah),max(ml_per_kah),min(min_ml_per_kah),max(max_ml_per_kah)
FROM lab.v_dosing_per_charge GROUP BY additive;
SELECT * FROM lab.v_etl_latest ORDER BY file_name,sheet_name,status;
SELECT * FROM lab.v_bi_nickel ORDER BY sampled_local;
