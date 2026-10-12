"""Generate the deliberately messy lab-journal source from this project's simulation.

Writes JSON for the artifact-tool workbook builder. Raw bath values are simulated.
"""
import json
import random
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from common import ROOT,connect,sources

TZ=ZoneInfo('Europe/Berlin')

def set_baseline(cur,phase):
    """Phase I from config/sources.yaml (Berlin dates, end excluded), checked against the stored analyses."""
    start,end,min_points=phase['start'],phase['end_exclusive'],int(phase['min_points'])
    period="tstzrange(%(start)s::date::timestamp AT TIME ZONE 'Europe/Berlin',%(end)s::date::timestamp AT TIME ZONE 'Europe/Berlin','[)')"
    short=cur.execute(f'''SELECT t.code,p.parameter_code,count(r.value) FROM ref.tank t CROSS JOIN lab.parameter p
      LEFT JOIN lab.analysis a ON a.tank_id=t.tank_id AND {period} @> a.sampled_at
      LEFT JOIN lab.analysis_result r ON r.analysis_id=a.analysis_id AND r.parameter_code=p.parameter_code
      WHERE t.process_code='ZNNI_ALK' GROUP BY 1,2 HAVING count(r.value)<%(min)s ORDER BY 1,2''',
      {'start':start,'end':end,'min':min_points}).fetchall()
    if short:
        raise SystemExit(f'Phase I {start}..{end} has fewer than {min_points} values for {short}; '
                         'adjust assumptions.spc_phase_one in config/sources.yaml to the simulated period')
    # Configuration is the source of truth; a changed period replaces the stored one (audited).
    cur.execute(f'''INSERT INTO lab.spc_baseline(tank_id,parameter_code,period,rationale,min_points)
      SELECT t.tank_id,p.parameter_code,{period},
      'Phase I chosen before the planted incident; checked separately from specification limits',%(min)s
      FROM ref.tank t CROSS JOIN lab.parameter p WHERE t.process_code='ZNNI_ALK'
      ON CONFLICT(tank_id,parameter_code) DO UPDATE SET period=EXCLUDED.period,min_points=EXCLUDED.min_points
      WHERE (lab.spc_baseline.period,lab.spc_baseline.min_points) IS DISTINCT FROM (EXCLUDED.period,EXCLUDED.min_points)''',
      {'start':start,'end':end,'min':min_points})

def main():
    rng=random.Random(7)
    config=sources()
    with connect('lab_journal_generator') as conn:
        analyses=conn.execute('''SELECT a.sampled_at,t.code,jsonb_object_agg(r.parameter_code,r.value)
          FROM lab.analysis a JOIN ref.tank t USING(tank_id) JOIN lab.analysis_result r USING(analysis_id)
          WHERE a.source='sim:p1' GROUP BY a.sampled_at,t.code ORDER BY a.sampled_at''').fetchall()
        cd=config['znni_alkaline']['current_density_a_dm2']['barrel'][0]
        # Integrate by local calendar-day overlap, including any midnight/DST crossing.
        daily=conn.execute('''WITH area AS (
          SELECT load_id,sum(ll.qty_pcs*p.area_dm2) AS dm2 FROM trace.load_lot ll
          JOIN trace.lot l USING(lot_id) JOIN ref.part p USING(part_id) GROUP BY load_id
        ), pieces AS (
          SELECT s.tank_id,d.day,a.dm2,d.slice
          FROM trace.load_step st JOIN ref.station s USING(station_id)
          JOIN ref.tank t USING(tank_id) JOIN area a USING(load_id)
          CROSS JOIN LATERAL lab.berlin_day_slices(st.in_station) d
          WHERE t.function='plate'
        ) SELECT tank_id,day,sum(dm2*%s*extract(epoch FROM upper(slice)-lower(slice))/3600)
        FROM pieces GROUP BY 1,2 ORDER BY 2''',(cd,)).fetchall()
        with conn.cursor() as cur:
            cur.executemany('''INSERT INTO lab.daily_charge VALUES(%s,%s,%s,'simulated area x current density x elapsed hours')
              ON CONFLICT(tank_id,day) DO UPDATE SET amp_hours=EXCLUDED.amp_hours''',daily)
            for additive in ('nickel_replenisher','brightener'):
                lo,hi=config['znni_alkaline']['additive_ml_per_1000_ah'][additive]
                cur.execute('''INSERT INTO lab.additive_reference VALUES(%s,%s,%s,'sharma_tds')
                  ON CONFLICT(additive) DO UPDATE SET min_ml_per_kah=EXCLUDED.min_ml_per_kah,max_ml_per_kah=EXCLUDED.max_ml_per_kah''',(additive,lo,hi))
            set_baseline(cur,config['assumptions']['spc_phase_one']['value'])
    columns=['ZN','NI','NAOH','NA2CO3','COD']
    head=['Datum','Uhrzeit','Bad','Zn [g/l]','Ni [g/l]','NaOH [g/l]','Na2CO3 [g/l]','CSB [g/l]','Bemerkung']
    rows=[['Laborjournal Zink-Nickel Linie 1'],['Simulierte Badwerte; absichtliche Eingabefehler für den ETL-Test.'],[],head]
    last_week=None
    for ts,tank,values in analyses:
        day=ts.astimezone(TZ)
        week=day.isocalendar().week
        if last_week is not None and week!=last_week:
            rows.append([f'Mittelwert KW {last_week}',None,None,None,None,None,None,None,'Zusammenfassungszeile, keine Messung'])
        last_week=week
        date_cell={'date':day.date().isoformat()} if rng.random()>.3 else day.strftime('%d.%m.%Y')
        time_cell=None if rng.random()<.05 else day.strftime('%H:%M')
        row=[date_cell,time_cell,rng.choice(['L1-T05','ZnNi 1','ZN-NI 1','Zink-Nickel L1','zinknickel l1 '])]
        for p in columns:
            value=float(values[p])
            row.append('n.b.' if p in ('NA2CO3','COD') and rng.random()<.04 else
                       str(value).replace('.',',') if rng.random()<.4 else value)
        row.append('simuliert')
        rows.append(row)
    # Guarantee every critical failure branch occurs in the delivered example.
    rows += [[],list(rows[4]),[rows[4][0],'06:00','L1-T05','10,0','1,3.5','120','70','115','Absichtlicher Tippfehler']]
    dosing=[['Dosierung Zink-Nickel Linie 1'],['Simulierte Tagesmengen; TDS-Verbrauch je kAh, keine reale Dosieranweisung.'],[],
            ['Datum','Uhrzeit','Bad','Zusatz','Menge','Einheit','Bemerkung']]
    for tank,day,ah in daily:
        for additive in ('nickel_replenisher','brightener'):
            ml=float(ah)/1000*rng.uniform(*config['znni_alkaline']['additive_ml_per_1000_ah'][additive])
            dosing.append([{'date':str(day)},'12:00','L1-T05',additive,f'{ml/1000:.6f}'.replace('.',','),'l','Tagesmenge, simuliert'])
    out=ROOT/'data/interim/journal.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'Analysen':rows,'Dosierung':dosing},ensure_ascii=False),encoding='utf-8')
    print(out.relative_to(ROOT).as_posix())

if __name__=='__main__':main()
