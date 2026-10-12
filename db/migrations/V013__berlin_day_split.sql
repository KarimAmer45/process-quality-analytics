-- Split a time interval at Berlin midnights (finding F-29). The expression is the one the journal
-- generator used inline; as a function it can be tested directly across both DST changes.
-- Each slice is the part of p_period that falls on one Berlin calendar day; empty slices are dropped.
CREATE OR REPLACE FUNCTION lab.berlin_day_slices(p_period tstzrange)
RETURNS TABLE(day date, slice tstzrange)
LANGUAGE sql STABLE AS $$
 SELECT x.day,x.slice FROM (
  SELECT d.day::date AS day,
  p_period * tstzrange(d.day::date::timestamp AT TIME ZONE 'Europe/Berlin',
    (d.day::date+1)::timestamp AT TIME ZONE 'Europe/Berlin','[)') AS slice
  FROM generate_series((lower(p_period) AT TIME ZONE 'Europe/Berlin')::date,
    (upper(p_period) AT TIME ZONE 'Europe/Berlin')::date,interval '1 day') d(day)
 ) x WHERE NOT isempty(x.slice) $$;
