-- V008 project 2: dosing log, Hull cell tests, Excel staging, SPC, real reference datasets

CREATE TABLE lab.dosing (
  dosing_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tank_id   int    NOT NULL REFERENCES ref.tank,
  dosed_at  timestamptz NOT NULL,
  additive  text   NOT NULL,                  -- 'nickel_replenisher', 'brightener', 'NaOH', ...
  amount    numeric(12,3) NOT NULL CHECK (amount > 0),
  unit      text   NOT NULL CHECK (unit IN ('L','mL','kg','g')),
  reason    text,
  source    text   NOT NULL
);
CREATE INDEX dosing_tank_time_idx ON lab.dosing (tank_id, dosed_at);

CREATE TABLE lab.hull_cell (
  test_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tank_id        int    NOT NULL REFERENCES ref.tank,
  tested_at      timestamptz NOT NULL,
  current_a      numeric(5,2) NOT NULL CHECK (current_a > 0),
  minutes        numeric(5,1) NOT NULL CHECK (minutes > 0),
  high_cd_result text,                         -- 'bright', 'burnt', ...
  low_cd_result  text,                         -- 'bright', 'dull', 'no deposit', ...
  notes          text
);

-- Raw rows exactly as read from a lab workbook. Nothing is lost, every row is explainable.
CREATE TABLE lab.stg_excel_row (
  file_name   text   NOT NULL,
  sheet_name  text   NOT NULL,
  row_no      int    NOT NULL,
  raw         jsonb  NOT NULL,
  loaded_at   timestamptz NOT NULL DEFAULT now(),
  status      text   NOT NULL DEFAULT 'new' CHECK (status IN ('new','loaded','duplicate','quarantined','ignored')),
  reason      text,
  PRIMARY KEY (file_name, sheet_name, row_no)
);

-- Individuals and moving range (I-MR) chart for one tank and parameter.
-- 2.66 = 3 / d2 and 3.267 = D4 for moving ranges of two points.
-- p_baseline: period used to compute the limits (phase I). NULL = all data.
CREATE OR REPLACE FUNCTION lab.imr_chart(p_tank_id int, p_parameter text, p_baseline tstzrange DEFAULT NULL)
RETURNS TABLE (analysis_id bigint, sampled_at timestamptz, value numeric, mr numeric,
               cl numeric, ucl numeric, lcl numeric, mr_ucl numeric, beyond_limits boolean)
LANGUAGE sql STABLE AS $$
  WITH s AS (
    SELECT a.analysis_id, a.sampled_at, r.value,
           abs(r.value - lag(r.value) OVER (ORDER BY a.sampled_at)) AS mr
      FROM lab.analysis a
      JOIN lab.analysis_result r ON r.analysis_id = a.analysis_id
     WHERE a.tank_id = p_tank_id AND r.parameter_code = p_parameter
  ),
  base AS (
    SELECT avg(s.value) AS xbar, avg(s.mr) AS mrbar
      FROM s
     WHERE p_baseline IS NULL OR p_baseline @> s.sampled_at
  )
  SELECT s.analysis_id, s.sampled_at, s.value, round(s.mr, 4),
         round(b.xbar, 4),
         round(b.xbar + 2.66 * b.mrbar, 4),
         round(b.xbar - 2.66 * b.mrbar, 4),
         round(3.267 * b.mrbar, 4),
         s.value > b.xbar + 2.66 * b.mrbar OR s.value < b.xbar - 2.66 * b.mrbar
    FROM s CROSS JOIN base b
   ORDER BY s.sampled_at;
$$;

-- Real reference data 1: NIST/SEMATECH lithography case study (450 rows, published answers)
CREATE TABLE realdata.nist_litho (
  cassette      smallint NOT NULL,
  wafer         smallint NOT NULL,
  site          smallint NOT NULL,
  raw_width     double precision NOT NULL,
  run_seq       int      NOT NULL,
  cleaned_width double precision,
  PRIMARY KEY (cassette, wafer, site)
);

-- Real reference data 2: UCI SECOM, 1,567 production runs x 590 anonymous sensors, long format
CREATE TABLE realdata.secom_run (
  run_id    int         PRIMARY KEY,
  run_at    timestamp   NOT NULL,                 -- source gives no time zone
  failed    boolean     NOT NULL
);
CREATE TABLE realdata.secom_value (
  run_id     int      NOT NULL REFERENCES realdata.secom_run,
  feature_no smallint NOT NULL CHECK (feature_no BETWEEN 1 AND 590),
  value      double precision NOT NULL,           -- missing values are simply absent rows
  PRIMARY KEY (feature_no, run_id)
);
