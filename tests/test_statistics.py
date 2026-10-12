from datetime import datetime,timedelta,timezone
import pytest
from validate_reference import validate

def add_series(db,values):
    line=db.execute("INSERT INTO ref.line(code,handling) VALUES('TEST','barrel') RETURNING line_id").fetchone()[0]
    tank=db.execute("INSERT INTO ref.tank(line_id,position,code,function,process_code) VALUES(%s,1,'TEST-T','plate','ZNNI_ALK') RETURNING tank_id",(line,)).fetchone()[0]
    start=datetime(2025,1,1,6,tzinfo=timezone.utc)
    for i,value in enumerate(values):
        aid=db.execute("INSERT INTO lab.analysis(tank_id,sampled_at,source) VALUES(%s,%s,'test') RETURNING analysis_id",(tank,start+timedelta(days=i))).fetchone()[0]
        db.execute("INSERT INTO lab.analysis_result VALUES(%s,'NI',%s,'AAS')",(aid,value))
    return tank,start

def test_real_nist_answers(db):assert all(row['passed'] for row in validate(db))

def test_real_secom_counts(db):
    assert db.execute('SELECT count(*),count(*) FILTER(WHERE failed) FROM realdata.secom_run').fetchone()==(1567,104)
    assert db.execute('SELECT count(*) FROM realdata.secom_value').fetchone()[0]==882579
    assert db.execute('SELECT count(*) FROM realdata.secom_feature_ranking').fetchone()[0]==590

def test_baseline_excludes_incoming_moving_range(db):
    tank,start=add_series(db,[100,10,12,8])
    # Two-point fixture baseline; the function's default minimum is 20 points, so state it.
    row=db.execute("SELECT cl,ucl FROM lab.imr_chart(%s,'NI',tstzrange(%s,%s),2) LIMIT 1",(tank,start+timedelta(days=1),start+timedelta(days=3))).fetchone()
    assert float(row[0])==11
    assert float(row[1])==pytest.approx(16.32)

def test_rule4_starts_at_eighth_point_and_equal_mean_breaks_run(db):
    tank,start=add_series(db,[0,1,-1]+[5]*8+[0]+[5]*7)
    # Three-point fixture baseline; it has to state its own minimum (the default is 20 points).
    db.execute("INSERT INTO lab.spc_baseline VALUES(%s,'NI',tstzrange(%s,%s),'test',3)",(tank,start,start+timedelta(days=3)))
    rows=db.execute('SELECT rule4_signal FROM lab.v_run_rules WHERE tank_id=%s ORDER BY sampled_at',(tank,)).fetchall()
    assert [i for i,row in enumerate(rows) if row[0]]==[10]

def test_cpk_splits_limit_versions(db):
    tank,start=add_series(db,[1,3,8,10])
    db.execute("INSERT INTO lab.parameter_limit(process_code,parameter_code,lsl,usl,valid_during,source) VALUES('ZNNI_ALK','NI',0,5,daterange('2025-01-01','2025-01-03'),'test'),('ZNNI_ALK','NI',5,15,daterange('2025-01-03','2025-02-01'),'test')")
    rows=db.execute('SELECT n,sigma_within,cpk FROM lab.v_monthly_capability WHERE tank_id=%s',(tank,)).fetchall()
    assert len(rows)==2 and all(r[0]==2 for r in rows)
    assert all(float(r[1])==pytest.approx(2/1.128) for r in rows)

def test_single_observation_has_no_cpk(db):
    tank,_=add_series(db,[1])
    assert db.execute('SELECT cpk FROM lab.v_monthly_capability WHERE tank_id=%s',(tank,)).fetchone()[0] is None

def test_secom_pre_failure_membership_uses_time_order(db):
    rows=db.execute('SELECT sequence_no,failed,before_failure FROM realdata.v_secom_window ORDER BY sequence_no').fetchall()
    fails={n for n,failed,_ in rows if failed}
    assert all(marked==any(n<failure<=n+20 for failure in fails) for n,_,marked in rows)

def test_dosing_within_reference_and_no_unexplained_rows(db):
    # Round-trip/unit check, not validation: the simulator generated the doses inside the TDS range,
    # so this confirms L/mL conversion, daily totals and charge normalization survive the import.
    assert db.execute('SELECT count(*) FROM lab.v_dosing_per_charge').fetchone()[0]==260
    assert not db.execute("SELECT 1 FROM lab.v_dosing_per_charge WHERE status<>'IN_RANGE'").fetchall()
    assert not db.execute("SELECT 1 FROM lab.stg_excel_row WHERE status<>'loaded' AND reason IS NULL").fetchall()

def test_readonly_cannot_change_lab_values(db):
    import psycopg
    db.execute('SET LOCAL ROLE role_readonly')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):db.execute('UPDATE lab.analysis_result SET value=value+1')
