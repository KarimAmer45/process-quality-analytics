"""Evidence protection, SPC baseline status, stability-aware capability and the Berlin day split."""
import psycopg
import pytest

def one(db,sql,*args):return db.execute(sql,args).fetchone()

def test_lab_role_cannot_move_or_delete_an_analysis_but_inserts_are_audited(db):
    tank=one(db,"SELECT tank_id FROM ref.tank WHERE code='L1-T05'")[0]
    db.execute('SET LOCAL ROLE role_lab')
    db.execute('SAVEPOINT s')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("UPDATE lab.analysis SET sampled_at=sampled_at-interval '30 days' WHERE analysis_id=44")
    db.execute('ROLLBACK TO SAVEPOINT s')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute('DELETE FROM lab.analysis WHERE analysis_id=44')
    db.execute('ROLLBACK TO SAVEPOINT s')
    # INSERT needs no UPDATE privilege: the validity trigger maintains the timeline with owner rights.
    aid=one(db,"INSERT INTO lab.analysis(tank_id,sampled_at,source) VALUES(%s,'2025-01-01 06:00+01','test') RETURNING analysis_id",tank)[0]
    db.execute('RESET ROLE')
    assert one(db,"SELECT count(*) FROM audit.change_log WHERE table_name='lab.analysis' AND operation='INSERT' AND row_pk->>'analysis_id'=%s",str(aid))[0]==1

def test_import_ledger_is_insert_only_for_application_roles(db):
    if not one(db,'SELECT count(*) FROM lab.import_file')[0]:pytest.skip('needs an applied import')
    statements=["UPDATE lab.stg_excel_row SET status='loaded' WHERE status='quarantined'",
                "UPDATE lab.import_file SET report='{}'",'DELETE FROM lab.stg_excel_row','TRUNCATE lab.import_file CASCADE']
    for role in ('role_lab','role_ingest','role_quality'):
        for statement in statements:
            db.execute('SAVEPOINT s');db.execute(f'SET LOCAL ROLE {role}')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):db.execute(statement)
            db.execute('ROLLBACK TO SAVEPOINT s')

def test_ledger_change_by_a_granted_role_is_still_refused_and_owner_changes_are_audited(db):
    if not one(db,'SELECT count(*) FROM lab.stg_excel_row WHERE status=%s','quarantined')[0]:pytest.skip('needs a quarantined row')
    db.execute('SAVEPOINT s')
    db.execute('GRANT UPDATE ON lab.stg_excel_row TO role_lab');db.execute('SET LOCAL ROLE role_lab')
    with pytest.raises(psycopg.errors.RaiseException,match='insert-only'):
        db.execute("UPDATE lab.stg_excel_row SET status='loaded' WHERE status='quarantined'")
    db.execute('ROLLBACK TO SAVEPOINT s')
    before=one(db,"SELECT count(*) FROM audit.change_log WHERE table_name='lab.stg_excel_row'")[0]
    changed=db.execute("UPDATE lab.stg_excel_row SET reason=reason||' (reviewed)' WHERE status='quarantined'").rowcount
    assert one(db,"SELECT count(*) FROM audit.change_log WHERE table_name='lab.stg_excel_row'")[0]==before+changed

def test_missing_or_moved_baseline_is_an_explicit_status_and_audited(db):
    if not one(db,"SELECT count(*) FROM lab.spc_baseline")[0]:pytest.skip('needs the demo baseline')
    assert {r[0] for r in db.execute("SELECT DISTINCT spc_status FROM lab.v_imr WHERE tank_code='L1-T05'")}=={'OK'}
    before=one(db,"SELECT count(*) FROM audit.change_log WHERE table_name='lab.spc_baseline'")[0]
    db.execute("UPDATE lab.spc_baseline SET period=tstzrange('2030-01-01','2030-02-01')")
    assert one(db,"SELECT count(*) FROM audit.change_log WHERE table_name='lab.spc_baseline'")[0]==before+5
    rows=db.execute("SELECT spc_status,cl,beyond_limits FROM lab.v_bi_imr WHERE tank_code='L1-T05' AND parameter_code='NI'").fetchall()
    assert len(rows)==130 and all(r==('NO_BASELINE',None,None) for r in rows)
    assert one(db,"SELECT DISTINCT spc_status FROM lab.v_bi_nickel")[0]=='NO_BASELINE'
    assert {r[0] for r in db.execute("SELECT DISTINCT interpretation FROM lab.v_monthly_capability WHERE tank_code='L1-T05' AND limit_id IS NOT NULL")}=={'NO_BASELINE_STABILITY_UNKNOWN'}
    db.execute("UPDATE lab.spc_baseline SET period=tstzrange('2026-03-02','2026-03-10')")
    assert one(db,"SELECT DISTINCT spc_status FROM lab.v_spc_status WHERE parameter_code='NI'")[0]=='INSUFFICIENT_BASELINE'
    db.execute("DELETE FROM lab.spc_baseline WHERE parameter_code='NI'")
    assert one(db,"SELECT spc_status,baseline_points FROM lab.v_spc_status WHERE tank_code='L1-T05' AND parameter_code='NI'")==('NO_BASELINE',0)

def test_capability_label_follows_the_signals_of_the_month(db):
    rows={(r[0],r[1].month):r[2:] for r in db.execute("""SELECT parameter_code,month,interpretation,small_sample,ppk
      FROM lab.v_monthly_capability WHERE tank_code='L1-T05' AND parameter_code IN ('NI','ZN')""")}
    if not rows:pytest.skip('needs the demo data')
    assert rows[('NI',4)][0]==rows[('NI',5)][0]==rows[('ZN',8)][0]=='UNSTABLE_SIGNALS_IN_MONTH'
    assert rows[('NI',3)][0]=='NO_SIGNALS_IN_MONTH' and rows[('NI',4)][2] is not None

def test_small_samples_are_flagged_but_reported(db):
    line=one(db,"INSERT INTO ref.line(code,handling) VALUES('TEST','barrel') RETURNING line_id")[0]
    tank=one(db,"INSERT INTO ref.tank(line_id,position,code,function,process_code) VALUES(%s,1,'TEST-T','plate','ZNNI_ALK') RETURNING tank_id",line)[0]
    for day,value in ((1,1.3),(2,1.5)):
        aid=one(db,"INSERT INTO lab.analysis(tank_id,sampled_at,source) VALUES(%s,%s,'test') RETURNING analysis_id",tank,f'2025-01-0{day} 06:00+01')[0]
        db.execute("INSERT INTO lab.analysis_result VALUES(%s,'NI',%s,'AAS')",(aid,value))
    db.execute("INSERT INTO lab.parameter_limit(process_code,parameter_code,lsl,usl,valid_during,source) VALUES('ZNNI_ALK','NI',1.1,2.0,daterange('2025-01-01','2025-02-01'),'test')")
    n,cpk,small,label=one(db,'SELECT n,cpk,small_sample,interpretation FROM lab.v_monthly_capability WHERE tank_id=%s',tank)
    assert n==2 and cpk is not None and small and label=='NO_BASELINE_STABILITY_UNKNOWN'

@pytest.mark.parametrize('zone',['Europe/Berlin','UTC','America/New_York','Pacific/Kiritimati'])
def test_berlin_midnight_split_across_both_dst_changes(db,zone):
    db.execute(f"SET LOCAL TimeZone='{zone}'")
    def hours(start,end):
        return [(str(d),float(h)) for d,h in db.execute("""SELECT day,extract(epoch FROM upper(slice)-lower(slice))/3600
          FROM lab.berlin_day_slices(tstzrange(%s::timestamp AT TIME ZONE 'Europe/Berlin',%s::timestamp AT TIME ZONE 'Europe/Berlin'))
          ORDER BY day""",(start,end))]
    # Autumn: 23:00 to 03:00 local spans five elapsed hours (02:00-03:00 occurs twice).
    assert hours('2026-10-24 23:00','2026-10-25 03:00')==[('2026-10-24',1.0),('2026-10-25',4.0)]
    # Spring: 23:00 to 04:00 local spans four elapsed hours (02:00-03:00 does not exist).
    assert hours('2026-03-28 23:00','2026-03-29 04:00')==[('2026-03-28',1.0),('2026-03-29',3.0)]
    # Ending exactly at midnight leaves no empty slice for the next day.
    assert hours('2026-05-01 22:00','2026-05-02 00:00')==[('2026-05-01',2.0)]

def test_owner_truncate_of_the_ledger_is_audited(db):
    rows=one(db,'SELECT count(*) FROM lab.import_file')[0]+one(db,'SELECT count(*) FROM lab.stg_excel_row')[0]
    if not rows:pytest.skip('needs an applied import')
    before=one(db,"SELECT count(*) FROM audit.change_log WHERE table_name IN ('lab.import_file','lab.stg_excel_row') AND operation='DELETE'")[0]
    db.execute('TRUNCATE lab.import_file CASCADE')
    assert one(db,"SELECT count(*) FROM audit.change_log WHERE table_name IN ('lab.import_file','lab.stg_excel_row') AND operation='DELETE'")[0]==before+rows
