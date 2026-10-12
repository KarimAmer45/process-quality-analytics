CREATE TABLE lab.import_file (
  sha256 text PRIMARY KEY CHECK(length(sha256)=64), file_name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now(), report jsonb NOT NULL
);
ALTER TABLE lab.stg_excel_row DROP CONSTRAINT stg_excel_row_pkey;
ALTER TABLE lab.stg_excel_row ADD COLUMN import_hash text NOT NULL REFERENCES lab.import_file;
ALTER TABLE lab.stg_excel_row ADD PRIMARY KEY(import_hash,sheet_name,row_no);
ALTER TABLE lab.dosing ADD COLUMN event_key text UNIQUE;
CREATE TRIGGER dosing_audit AFTER INSERT OR UPDATE OR DELETE ON lab.dosing
  FOR EACH ROW EXECUTE FUNCTION audit.log_change('dosing_id');
CREATE TABLE lab.daily_charge (
  tank_id int REFERENCES ref.tank, day date, amp_hours numeric NOT NULL CHECK(amp_hours>0),
  origin text NOT NULL, PRIMARY KEY(tank_id,day)
);
CREATE TABLE lab.additive_reference (
  additive text PRIMARY KEY, min_ml_per_kah numeric, max_ml_per_kah numeric, source text NOT NULL
);
CREATE TABLE lab.spc_baseline (
  tank_id int REFERENCES ref.tank, parameter_code text REFERENCES lab.parameter,
  period tstzrange NOT NULL, rationale text NOT NULL, PRIMARY KEY(tank_id,parameter_code)
);

-- Never let a moving range reaching in from outside Phase I contaminate its limits.
CREATE OR REPLACE FUNCTION lab.imr_chart(p_tank_id int,p_parameter text,p_baseline tstzrange DEFAULT NULL)
RETURNS TABLE(analysis_id bigint,sampled_at timestamptz,value numeric,mr numeric,
  cl numeric,ucl numeric,lcl numeric,mr_ucl numeric,beyond_limits boolean)
LANGUAGE sql STABLE AS $$
WITH s AS (
 SELECT a.analysis_id,a.sampled_at,r.value,
 lag(a.sampled_at) OVER(ORDER BY a.sampled_at) AS previous_at,
 abs(r.value-lag(r.value) OVER(ORDER BY a.sampled_at)) AS mr
 FROM lab.analysis a JOIN lab.analysis_result r USING(analysis_id)
 WHERE a.tank_id=p_tank_id AND r.parameter_code=p_parameter
), b AS (
 SELECT avg(value) AS xbar,
 avg(mr) FILTER(WHERE p_baseline IS NULL OR p_baseline @> previous_at) AS mrbar
 FROM s WHERE p_baseline IS NULL OR p_baseline @> sampled_at
)
SELECT s.analysis_id,s.sampled_at,s.value,s.mr,b.xbar,b.xbar+2.66*b.mrbar,
 b.xbar-2.66*b.mrbar,3.267*b.mrbar,
 s.value>b.xbar+2.66*b.mrbar OR s.value<b.xbar-2.66*b.mrbar
FROM s CROSS JOIN b ORDER BY s.sampled_at $$;

CREATE VIEW lab.v_imr AS
SELECT b.tank_id,t.code AS tank_code,b.parameter_code,c.*
FROM lab.spc_baseline b JOIN ref.tank t USING(tank_id)
CROSS JOIN LATERAL lab.imr_chart(b.tank_id,b.parameter_code,b.period) c;

-- Gaps/islands; equality to CL interrupts a run. Signal at point 8, never retroactively.
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

-- Split by calendar month AND limit version; no MR crosses either boundary.
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
 avg(value) AS mean,avg(moving_range)/1.128 AS sigma_within FROM mr GROUP BY 1,2,3,4,5,6,7
)
SELECT *,CASE WHEN n<2 OR sigma_within IS NULL OR sigma_within=0 OR limit_id IS NULL THEN NULL
 ELSE least((usl-mean)/(3*sigma_within),(mean-lsl)/(3*sigma_within)) END AS cpk,
 CASE WHEN limit_id IS NULL THEN 'NO_LIMIT' WHEN n<2 THEN 'INSUFFICIENT_DATA'
 WHEN sigma_within=0 THEN 'ZERO_VARIATION' ELSE 'DESCRIPTIVE_ONLY_CHECK_STABILITY' END AS interpretation
FROM stats;

CREATE VIEW realdata.v_nist_summary AS
SELECT count(*) AS n,avg(raw_width) AS mean,stddev_samp(raw_width) AS sd,
 percentile_cont(0.5) WITHIN GROUP(ORDER BY raw_width) AS median,min(raw_width) AS minimum,max(raw_width) AS maximum
FROM realdata.nist_litho;

CREATE VIEW realdata.v_nist_anova AS
WITH enriched AS (
 SELECT *,avg(raw_width) OVER() AS grand_mean,
 avg(raw_width) OVER(PARTITION BY cassette) AS cassette_mean,
 avg(raw_width) OVER(PARTITION BY cassette,wafer) AS wafer_mean
 FROM realdata.nist_litho
), sums AS (
 SELECT sum(power(cassette_mean-grand_mean,2)) AS cassette_ss,
 sum(power(wafer_mean-cassette_mean,2)) AS wafer_ss,
 sum(power(raw_width-wafer_mean,2)) AS site_ss,
 count(DISTINCT cassette)-1 AS cassette_df,
 count(DISTINCT(cassette,wafer))-count(DISTINCT cassette) AS wafer_df,
 count(*)-count(DISTINCT(cassette,wafer)) AS site_df,
 count(*)::float/nullif(count(DISTINCT cassette),0) AS per_cassette,
 count(*)::float/nullif(count(DISTINCT(cassette,wafer)),0) AS per_wafer
 FROM enriched
), ms AS (
 SELECT *,cassette_ss/nullif(cassette_df,0) AS cassette_ms,
 wafer_ss/nullif(wafer_df,0) AS wafer_ms,site_ss/nullif(site_df,0) AS site_ms FROM sums
)
SELECT 'Cassette' AS component,cassette_df AS df,cassette_ss AS ss,cassette_ms AS ms,
 (cassette_ms-wafer_ms)/per_cassette AS variance_component FROM ms
UNION ALL SELECT 'Wafer within cassette',wafer_df,wafer_ss,wafer_ms,(wafer_ms-site_ms)/per_wafer FROM ms
UNION ALL SELECT 'Site within wafer',site_df,site_ss,site_ms,site_ms FROM ms;

-- Timestamp order, original row ID breaks ties. Exclude the failure itself from its own
-- preceding window. Overlapping windows count each run once. This is retrospective.
CREATE VIEW realdata.v_secom_window AS
WITH ordered AS (
 SELECT *,row_number() OVER(ORDER BY run_at,run_id) AS sequence_no FROM realdata.secom_run
)
SELECT o.*,EXISTS(SELECT 1 FROM ordered f WHERE f.failed AND f.sequence_no>o.sequence_no
 AND f.sequence_no<=o.sequence_no+20) AS before_failure FROM ordered o;

CREATE MATERIALIZED VIEW realdata.secom_feature_ranking AS
WITH stats AS (
 SELECT feature_no,count(*) FILTER(WHERE before_failure) AS n_before,
 count(*) FILTER(WHERE NOT before_failure) AS n_other,
 avg(value) FILTER(WHERE before_failure) AS mean_before,
 avg(value) FILTER(WHERE NOT before_failure) AS mean_other,
 var_samp(value) FILTER(WHERE before_failure) AS var_before,
 var_samp(value) FILTER(WHERE NOT before_failure) AS var_other
 FROM realdata.secom_value JOIN realdata.v_secom_window USING(run_id) GROUP BY feature_no
), pooled AS (
 SELECT *,sqrt(((n_before-1)*var_before+(n_other-1)*var_other)/nullif(n_before+n_other-2,0)) AS pooled_sd FROM stats
)
SELECT f.feature_no,p.n_before,p.n_other,p.mean_before,p.mean_other,p.pooled_sd,
 CASE WHEN p.n_before>=2 AND p.n_other>=2 THEN (p.mean_before-p.mean_other)/nullif(p.pooled_sd,0) END AS effect_size,
 CASE WHEN p.feature_no IS NULL THEN 'ALL_MISSING' WHEN p.n_before<2 OR p.n_other<2 THEN 'INSUFFICIENT_DATA'
 WHEN p.pooled_sd=0 THEN 'CONSTANT' ELSE 'EXPLORATORY' END AS status
FROM generate_series(1,590) f(feature_no) LEFT JOIN pooled p USING(feature_no) WITH NO DATA;
CREATE UNIQUE INDEX secom_ranking_feature_idx ON realdata.secom_feature_ranking(feature_no);

CREATE VIEW lab.v_dosing_per_charge AS
WITH doses AS (
 SELECT tank_id,(dosed_at AT TIME ZONE 'Europe/Berlin')::date AS day,additive,
 sum(CASE unit WHEN 'L' THEN amount*1000 WHEN 'mL' THEN amount END) AS ml
 FROM lab.dosing GROUP BY 1,2,3
)
SELECT d.*,t.code AS tank_code,c.amp_hours,c.origin AS charge_origin,d.ml/(c.amp_hours/1000) AS ml_per_kah,
 r.min_ml_per_kah,r.max_ml_per_kah,r.source,
 CASE WHEN c.amp_hours IS NULL THEN 'NO_CHARGE' WHEN r.additive IS NULL THEN 'NO_REFERENCE'
 WHEN d.ml/(c.amp_hours/1000) BETWEEN r.min_ml_per_kah AND r.max_ml_per_kah THEN 'IN_RANGE' ELSE 'OUTSIDE_RANGE' END AS status
FROM doses d JOIN ref.tank t USING(tank_id)
LEFT JOIN lab.daily_charge c USING(tank_id,day) LEFT JOIN lab.additive_reference r USING(additive);

CREATE VIEW lab.v_etl_status AS SELECT f.file_name,s.import_hash,s.sheet_name,s.status,s.reason,count(*) AS rows
FROM lab.stg_excel_row s JOIN lab.import_file f ON f.sha256=s.import_hash GROUP BY 1,2,3,4,5;
CREATE VIEW lab.v_bi_imr AS SELECT *,sampled_at AT TIME ZONE 'Europe/Berlin' AS sampled_local FROM lab.v_run_rules;
CREATE VIEW realdata.v_secom_ranking AS SELECT * FROM realdata.secom_feature_ranking;
