"""Compare independent published NIST answers with PostgreSQL calculations."""
import json
import math
import pathlib
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ingest'))
from common import connect

def validate(conn):
    cur=conn.execute('SELECT * FROM realdata.v_nist_summary')
    summary=dict(zip([c.name for c in cur.description],cur.fetchone()))
    target={'n':450,'mean':2.53228,'sd':0.69376,'median':2.45334,'minimum':0.74655,'maximum':5.16867}
    checks=[]
    for key,expected in target.items():
        actual=summary[key]
        checks.append({'metric':key,'actual':actual,'published':expected,'passed':math.isclose(actual,expected,rel_tol=0,abs_tol=5e-6)})
    targets={'Cassette':(29,127.40293,0.2645),'Wafer within cassette':(60,25.52089,0.0500),'Site within wafer':(360,63.17865,0.1755)}
    for component,df,ss,ms,vc in conn.execute('SELECT * FROM realdata.v_nist_anova'):
        tdf,tss,tvc=targets[component]
        for metric,actual,expected,tol in [('df',df,tdf,0),('ss',ss,tss,5e-6),('variance_component',vc,tvc,5e-5)]:
            checks.append({'metric':component+' '+metric,'actual':actual,'published':expected,'passed':math.isclose(actual,expected,rel_tol=0,abs_tol=tol)})
    return checks

if __name__=='__main__':
    with connect('validate_nist') as conn: checks=validate(conn)
    (ROOT/'docs/results/nist_validation.json').write_text(json.dumps(checks,indent=2))
    if not all(c['passed'] for c in checks): raise SystemExit('NIST validation failed; see nist_validation.json')
    print(f'{len(checks)} published NIST values reproduced within printed precision')
