"""End-to-end reproducible example against the database selected by libpq variables."""
import os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ingest'))
from common import connect

def main():
    steps=['scripts/migrate.py','ingest/p1_simulate_plant.py','scripts/download_data.py',
           'ingest/reference_data.py','ingest/journal_payload.py','scripts/make_journal.py',
           'ingest/etl_lab_journal.py']
    # The foundation simulator intentionally starts from an empty database.
    # Preserve an existing demonstration rather than reseeding over audit history.
    with connect('demo_check') as conn:
        seeded=conn.execute("SELECT to_regclass('trace.lot')").fetchone()[0]
        seeded=bool(seeded and conn.execute('SELECT EXISTS(SELECT 1 FROM trace.lot)').fetchone()[0])
    for step in steps:
        if seeded and step=='ingest/p1_simulate_plant.py':continue
        subprocess.run([sys.executable,str(ROOT/step)],cwd=ROOT,check=True)
    for step,args in [('ingest/etl_lab_journal.py',['--apply']),('scripts/validate_reference.py',[]),
                      ('scripts/export_results.py',[]),('scripts/build_powerbi.py',[])]:
        subprocess.run([sys.executable,str(ROOT/step),*args],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','pytest','-q','tests'],cwd=ROOT,check=True)

if __name__=='__main__':main()
