-- SPC baseline status (finding F-19), stability-aware capability with Ppk (F-28),
-- signal markers for the Power BI nickel chart (F-30) and auditing of SPC configuration.

-- 1. A baseline needs a minimum number of points before its limits are used. 20 individual
--    values is the usual minimum for Phase I individuals-chart limits; the demo baseline has 32.
ALTER TABLE lab.spc_baseline
  ADD COLUMN min_points int NOT NULL DEFAULT 20 CHECK (min_points >= 2);

DROP TRIGGER IF EXISTS spc_baseline_audit ON lab.spc_baseline;
CREATE TRIGGER spc_baseline_audit AFTER INSERT OR UPDATE OR DELETE ON lab.spc_baseline
  FOR EACH ROW EXECUTE FUNCTION audit.log_change('tank_id', 'parameter_code');
DROP TRIGGER IF EXISTS additive_reference_audit ON lab.additive_reference;
CREATE TRIGGER additive_reference_audit AFTER INSERT OR UPDATE OR DELETE ON lab.additive_reference
  FOR EACH ROW EXECUTE FUNCTION audit.log_change('additive');

-- 2. The chart function reports how many points its baseline holds and an explicit status.
--    Limits and breach flags are only produced when the baseline has at least p_min_points values
--    (default 20, the same as spc_baseline.min_points); otherwise they stay NULL and spc_status
--    says why (NO_BASELINE or INSUFFICIENT_BASELINE). Small test fixtures pass a lower minimum.
DROP VIEW lab.v_bi_capability, lab.v_monthly_capability, lab.v_bi_nickel, lab.v_rule4_runs,
  lab.v_bi_imr, lab.v_run_rules, lab.v_imr;
DROP FUNCTION lab.imr_chart(int, text, tstzrange);

CREATE FUNCTION lab.imr_chart(p_tank_id int, p_parameter text, p_baseline tstzrange DEFAULT NULL,
  p_min_points int DEFAULT 20)
RETURNS TABLE(analysis_id bigint, sampled_at timestamptz, value numeric, mr numeric,
  cl numeric, ucl numeric, lcl numeric, mr_ucl numeric, beyond_limits boolean,
  baseline_points bigint, spc_status text)
LANGUAGE sql STABLE AS $$
WITH s AS (
 SELECT a.analysis_id,a.sampled_at,r.value,
 lag(a.sampled_at) OVER(ORDER BY a.sampled_at) AS previous_at,
 abs(r.value-lag(r.value) OVER(ORDER BY a.sampled_at)) AS mr
 FROM lab.analysis a JOIN lab.analysis_result r USING(analysis_id)
 WHERE a.tank_id=p_tank_id AND r.parameter_code=p_parameter
), raw AS (
 SELECT count(*) AS n_base,avg(value) AS xbar,
 avg(mr) FILTER(WHERE p_baseline IS NULL OR p_baseline @> previous_at) AS mrbar
 FROM s WHERE p_baseline IS NULL OR p_baseline @> sampled_at
), b AS (
 SELECT n_base,
 CASE WHEN n_base>=p_min_points AND mrbar IS NOT NULL THEN xbar END AS xbar,
 CASE WHEN n_base>=p_min_points AND mrbar IS NOT NULL THEN mrbar END AS mrbar,
 CASE WHEN n_base=0 THEN 'NO_BASELINE'
      WHEN n_base<p_min_points OR mrbar IS NULL THEN 'INSUFFICIENT_BASELINE'
      ELSE 'OK' END AS status
 FROM raw
)
SELECT s.analysis_id,s.sampled_at,s.value,s.mr,b.xbar,b.xbar+2.66*b.mrbar,
 b.xbar-2.66*b.mrbar,3.267*b.mrbar,
 s.value>b.xbar+2.66*b.mrbar OR s.value<b.xbar-2.66*b.mrbar,
 b.n_base,b.status
FROM s CROSS JOIN b ORDER BY s.sampled_at $$;

-- Every tank/parameter that has results appears, with or without a baseline row; a missing
-- baseline row is reported as NO_BASELINE instead of silently dropping the parameter.
-- (A baseline row for a parameter without any results has no points and therefore no rows.)
CREATE VIEW lab.v_imr AS
WITH pairs AS (
 SELECT DISTINCT a.tank_id,r.parameter_code FROM lab.analysis a JOIN lab.analysis_result r USING(analysis_id)
 UNION SELECT tank_id,parameter_code FROM lab.spc_baseline
)
SELECT p.tank_id,t.code AS tank_code,p.parameter_code,c.*
FROM pairs p JOIN ref.tank t USING(tank_id)
LEFT JOIN lab.spc_baseline b USING(tank_id,parameter_code)
CROSS JOIN LATERAL lab.imr_chart(p.tank_id,p.parameter_code,coalesce(b.period,'empty'::tstzrange),
  coalesce(b.min_points,20)) c;

-- Gaps/islands; equality to CL interrupts a run. Signal at point 8, never retroactively.
-- Without a usable baseline, side and rule4_signal are NULL and spc_status explains it.
CREATE VIEW lab.v_run_rules AS
WITH signed AS (
 SELECT *,sign(value-cl) AS side FROM lab.v_imr
), islands AS (
 SELECT *,row_number() OVER(PARTITION BY tank_id,parameter_code ORDER BY sampled_at)
 -row_number() OVER(PARTITION BY tank_id,parameter_code,side ORDER BY sampled_at) AS grp
 FROM signed
), runs AS (
 SELECT *,row_number() OVER(PARTITION BY tank_id,parameter_code,side,grp ORDER BY sampled_at) AS run_length
 FROM islands
)
SELECT *,side<>0 AND run_length>=8 AS rule4_signal FROM runs;

CREATE VIEW lab.v_bi_imr AS SELECT *,sampled_at AT TIME ZONE 'Europe/Berlin' AS sampled_local FROM lab.v_run_rules;

-- signal_value repeats the value only at individuals-limit breaches or Rule 4 signals, so a
-- chart can draw it as markers on top of the line.
CREATE VIEW lab.v_bi_nickel AS
SELECT tank_code,sampled_local,value,mr,cl,ucl,lcl,mr_ucl,beyond_limits,rule4_signal,spc_status,
 CASE WHEN beyond_limits OR rule4_signal THEN value END AS signal_value
FROM lab.v_bi_imr WHERE tank_code='L1-T05' AND parameter_code='NI';

CREATE VIEW lab.v_rule4_runs AS
SELECT tank_code,parameter_code,side,grp,min(sampled_at) AS run_start,
 max(sampled_at) AS run_end,count(*) AS observations,
 min(sampled_at) FILTER(WHERE rule4_signal) AS first_signal,
 count(*) FILTER(WHERE rule4_signal) AS signal_count
FROM lab.v_run_rules WHERE side<>0
GROUP BY tank_code,parameter_code,side,grp HAVING bool_or(rule4_signal);

-- One row per tank/parameter that has results: baseline period and minimum, the number of
-- baseline points, spc_status, and the limits (NULL unless spc_status is OK).
CREATE VIEW lab.v_spc_status AS
SELECT DISTINCT ON (i.tank_id,i.parameter_code) i.tank_id,i.tank_code,i.parameter_code,
 b.period AS baseline_period,coalesce(b.min_points,20) AS min_points,i.baseline_points,i.spc_status,
 i.cl,i.lcl,i.ucl,i.mr_ucl
FROM lab.v_imr i LEFT JOIN lab.spc_baseline b USING(tank_id,parameter_code)
ORDER BY i.tank_id,i.parameter_code;

-- 3. Capability per calendar month and limit version (unchanged split; no MR crosses either
--    boundary), now with overall sigma and Ppk, the signal counts of that month, a small-sample
--    flag (n < 20, still reported) and a label driven by the month's actual signals.
--    Signals are counted per tank, parameter and Berlin calendar month: when limits change
--    mid-month, both limit-version rows of that month carry the same signal counts and label.
CREATE VIEW lab.v_monthly_capability AS
WITH paired AS (
 SELECT t.tank_id,t.code AS tank_code,r.parameter_code,
 date_trunc('month',a.sampled_at AT TIME ZONE 'Europe/Berlin')::date AS month,
 l.limit_id,l.lsl,l.usl,a.sampled_at,r.value
 FROM lab.analysis a JOIN ref.tank t USING(tank_id)
 JOIN lab.analysis_result r USING(analysis_id)
 LEFT JOIN lab.parameter_limit l ON l.process_code=t.process_code AND l.parameter_code=r.parameter_code
 AND l.valid_during @> (a.sampled_at AT TIME ZONE 'Europe/Berlin')::date
), mr AS (
 SELECT *,abs(value-lag(value) OVER(PARTITION BY tank_id,parameter_code,month,limit_id ORDER BY sampled_at)) AS moving_range FROM paired
), stats AS (
 SELECT tank_id,tank_code,parameter_code,month,limit_id,lsl,usl,count(*) AS n,
 avg(value) AS mean,avg(moving_range)/1.128 AS sigma_within,stddev_samp(value) AS sigma_overall
 FROM mr GROUP BY 1,2,3,4,5,6,7
), signals AS (
 SELECT tank_id,parameter_code,date_trunc('month',sampled_at AT TIME ZONE 'Europe/Berlin')::date AS month,
 count(*) FILTER(WHERE beyond_limits) AS i_chart_breaches,
 count(*) FILTER(WHERE rule4_signal) AS rule4_points,
 count(*) FILTER(WHERE mr>mr_ucl) AS mr_excursions,
 bool_and(spc_status='OK') AS baseline_ok
 FROM lab.v_run_rules GROUP BY 1,2,3
)
SELECT s.tank_id,s.tank_code,s.parameter_code,s.month,s.limit_id,s.lsl,s.usl,s.n,s.mean,s.sigma_within,
 CASE WHEN s.n<2 OR s.sigma_within IS NULL OR s.sigma_within=0 OR s.limit_id IS NULL THEN NULL
 ELSE least((s.usl-s.mean)/(3*s.sigma_within),(s.mean-s.lsl)/(3*s.sigma_within)) END AS cpk,
 CASE WHEN s.limit_id IS NULL THEN 'NO_LIMIT' WHEN s.n<2 THEN 'INSUFFICIENT_DATA'
 WHEN s.sigma_within=0 THEN 'ZERO_VARIATION'
 WHEN NOT coalesce(g.baseline_ok,false) THEN 'NO_BASELINE_STABILITY_UNKNOWN'
 WHEN g.i_chart_breaches+g.rule4_points>0 THEN 'UNSTABLE_SIGNALS_IN_MONTH'
 ELSE 'NO_SIGNALS_IN_MONTH' END AS interpretation,
 s.sigma_overall,
 CASE WHEN s.n<2 OR s.sigma_overall IS NULL OR s.sigma_overall=0 OR s.limit_id IS NULL THEN NULL
 ELSE least((s.usl-s.mean)/(3*s.sigma_overall),(s.mean-s.lsl)/(3*s.sigma_overall)) END AS ppk,
 s.n<20 AS small_sample,
 coalesce(g.i_chart_breaches,0) AS i_chart_breaches,coalesce(g.rule4_points,0) AS rule4_points,
 coalesce(g.mr_excursions,0) AS mr_excursions
FROM stats s LEFT JOIN signals g USING(tank_id,parameter_code,month);

CREATE VIEW lab.v_bi_capability AS
SELECT tank_code,parameter_code,month,n,mean,sigma_within,lsl,usl,cpk,interpretation,
 sigma_overall,ppk,small_sample,i_chart_breaches,rule4_points,mr_excursions
FROM lab.v_monthly_capability WHERE tank_code='L1-T05';

GRANT SELECT ON ALL TABLES IN SCHEMA lab TO role_readonly,role_lab,role_quality;
