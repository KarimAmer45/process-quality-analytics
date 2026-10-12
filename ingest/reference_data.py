"""Strict real-data loaders; validation precedes writes; imports are transactional."""
import json
import math
from datetime import datetime
import numpy as np
from common import ROOT,connect

def parse_nist(path):
    lines=path.read_text(encoding='latin-1').splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith('-----'))+1
    rows=[]
    for line in lines[start:]:
        if not line.strip(): continue
        vals=list(map(float,line.split()))
        if len(vals)!=6 or not all(math.isfinite(v) for v in vals): raise ValueError('Invalid NIST record')
        c,w,s,raw,seq,clean=vals
        if any(v!=int(v) for v in (c,w,s,seq)): raise ValueError('Nonintegral NIST key')
        rows.append((int(c),int(w),int(s),raw,int(seq),clean))
    expected={(c,w,s) for c in range(1,31) for w in range(1,4) for s in range(1,6)}
    if len(rows)!=450 or {r[:3] for r in rows}!=expected: raise ValueError('NIST topology differs from 30 x 3 x 5')
    if len({r[4] for r in rows})!=450: raise ValueError('Duplicate NIST sequence')
    if not math.isclose(sum(r[3] for r in rows)/450,2.53228,abs_tol=5e-6): raise ValueError('NIST mean differs')
    return rows

def parse_secom(directory):
    labels=[]
    for i,line in enumerate((directory/'secom_labels.data').read_text().splitlines(),1):
        label,stamp=line.split(maxsplit=1)
        if label not in ('-1','1'): raise ValueError('Unknown SECOM outcome')
        labels.append((i,datetime.strptime(stamp.strip('"'),'%d/%m/%Y %H:%M:%S'),label=='1'))
    data=np.loadtxt(directory/'secom.data')
    if data.shape!=(1567,590) or len(labels)!=1567: raise ValueError(f'SECOM shape differs: {data.shape}')
    if sum(row[2] for row in labels)!=104 or np.isinf(data).any(): raise ValueError('SECOM labels/values differ')
    return labels,data

def main():
    nist=parse_nist(ROOT/'data/raw/nist/LITHOGRA.DAT')
    labels,data=parse_secom(ROOT/'data/raw/secom')
    with connect('reference_loader') as conn:
        with conn.cursor() as cur:
            cur.executemany('''INSERT INTO realdata.nist_litho VALUES(%s,%s,%s,%s,%s,%s)
              ON CONFLICT(cassette,wafer,site) DO UPDATE SET raw_width=EXCLUDED.raw_width,
              run_seq=EXCLUDED.run_seq,cleaned_width=EXCLUDED.cleaned_width''',nist)
            cur.executemany('''INSERT INTO realdata.secom_run VALUES(%s,%s,%s) ON CONFLICT(run_id)
              DO UPDATE SET run_at=EXCLUDED.run_at,failed=EXCLUDED.failed''',labels)
            cur.execute('CREATE TEMP TABLE incoming_secom (LIKE realdata.secom_value INCLUDING ALL) ON COMMIT DROP')
            with cur.copy('COPY incoming_secom FROM STDIN') as cp:
                for i,row in enumerate(data,1):
                    for j,v in enumerate(row,1):
                        if not np.isnan(v): cp.write_row((i,j,float(v)))
            cur.execute('DELETE FROM realdata.secom_value v WHERE NOT EXISTS(SELECT 1 FROM incoming_secom s WHERE s.run_id=v.run_id AND s.feature_no=v.feature_no)')
            cur.execute('''INSERT INTO realdata.secom_value SELECT * FROM incoming_secom
              ON CONFLICT(feature_no,run_id) DO UPDATE SET value=EXCLUDED.value
              WHERE realdata.secom_value.value IS DISTINCT FROM EXCLUDED.value''')
            cur.execute('ANALYZE realdata.secom_run; ANALYZE realdata.secom_value')
            cur.execute('REFRESH MATERIALIZED VIEW realdata.secom_feature_ranking')
    report={'nist_rows':len(nist),'secom_runs':len(labels),'secom_sensors':data.shape[1],
            'secom_failures':104,'secom_values':int(np.isfinite(data).sum()),
            'missing_values':int(np.isnan(data).sum()),'missing_pct':float(np.isnan(data).mean()*100),
            'first_test_time':str(min(r[1] for r in labels)),'last_test_time':str(max(r[1] for r in labels)),
            'metadata_note':'UCI page says 591 features; the downloaded measurement matrix has 590 sensor columns. Timestamp and outcome remain separate.'}
    (ROOT/'docs/results/reference_import.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
