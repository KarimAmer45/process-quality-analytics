"""Build twice in an isolated, temporary database; never reset the working database."""
import json,os,pathlib,subprocess,sys,time,uuid
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    name='bath_verify_'+uuid.uuid4().hex[:12]
    params=conninfo_to_dict(os.environ.get('DATABASE_URL',''))
    params['dbname']=name
    started=time.monotonic();report={'database':name,'runs':[],'temporary_database_removed':False}
    with psycopg.connect(os.environ.get('DATABASE_URL',''),autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            env={**os.environ,'DATABASE_URL':make_conninfo(**params),'PGDATABASE':name}
            counts=[]
            for run in (1,2):
                proc=subprocess.run([sys.executable,str(ROOT/'scripts/demo.py')],cwd=ROOT,env=env,capture_output=True,text=True)
                log=ROOT/f'docs/results/clean_run_{run}.log';log.write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
                report['runs'].append({'run':run,'returncode':proc.returncode,'log':log.name})
                if proc.returncode:raise RuntimeError(f'Clean run {run} failed; inspect {log}')
                with psycopg.connect(**params) as check:
                    counts.append({t:check.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*t.split('.')))).fetchone()[0]
                        for t in ['trace.lot','lab.analysis','lab.analysis_result','lab.dosing','realdata.nist_litho','realdata.secom_run','realdata.secom_value']})
                print(f'Clean run {run} passed: {counts[-1]}',flush=True)
            assert counts[0]==counts[1],counts
            report['business_counts']=counts;report['stable_on_repeat']=True
        finally:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
            report['temporary_database_removed']=True;report['elapsed_seconds']=round(time.monotonic()-started,2)
            (ROOT/'docs/results/clean_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
