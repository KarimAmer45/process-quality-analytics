"""Download the two public reference datasets; preserve originals and record hashes."""
import hashlib
import json
import pathlib
import urllib.request
import zipfile
from datetime import datetime,timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCES={
 'nist/LITHOGRA.DAT':'https://www.itl.nist.gov/div898/handbook/datasets/LITHOGRA.DAT',
 'secom/secom.zip':'https://archive.ics.uci.edu/static/public/179/secom.zip',
}

def main():
    records=[]
    for name,url in SOURCES.items():
        path=ROOT/'data/raw'/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            request=urllib.request.Request(url,headers={'User-Agent':'BathLabPortfolio/1.0'})
            with urllib.request.urlopen(request,timeout=60) as response:
                content=response.read()
            path.write_bytes(content)
        records.append({'path':'data/raw/'+name,'url':url,'bytes':path.stat().st_size,
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    with zipfile.ZipFile(ROOT/'data/raw/secom/secom.zip') as archive:
        for name in ('secom.data','secom_labels.data','secom.names'):
            content=archive.read(name)
            (ROOT/'data/raw/secom'/name).write_bytes(content)
            records.append({'path':'data/raw/secom/'+name,'from_archive':'secom.zip',
                            'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
    out=ROOT/'docs/results/download_manifest.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'files':records},indent=2))
    print(out.relative_to(ROOT).as_posix())

if __name__=='__main__': main()
