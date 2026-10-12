"""Cache Microsoft's public PBIR schemas and their referenced definitions."""
import hashlib,json,pathlib,urllib.request,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=ROOT/'.local/pbir-schemas'
BASE='https://developer.microsoft.com/json-schemas/'
ROOTS=['fabric/pbip/pbipProperties/1.0.0/schema.json',
 'fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',
 'fabric/item/report/definitionProperties/2.0.0/schema.json',
 'fabric/item/report/definition/versionMetadata/1.0.0/schema.json',
 'fabric/item/report/definition/report/1.0.0/schema.json',
 'fabric/item/report/definition/pagesMetadata/1.0.0/schema.json',
 'fabric/item/report/definition/page/1.0.0/schema.json',
 'fabric/item/report/definition/visualContainer/1.0.0/schema.json']

def fetch(url,seen):
    if url in seen:return
    seen.add(url)
    if not url.startswith(BASE):raise ValueError('Unexpected schema host')
    relative=url.removeprefix(BASE)
    path=CACHE/relative
    if not path.exists():
        data=urllib.request.urlopen('https://raw.githubusercontent.com/microsoft/json-schemas/main/'+relative,timeout=60).read()
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    schema=json.loads(path.read_text())
    def walk(obj):
        if isinstance(obj,dict):
            if '$ref' in obj and not obj['$ref'].startswith('#'):
                fetch(urllib.parse.urljoin(url,obj['$ref']).split('#')[0],seen)
            for v in obj.values():walk(v)
        elif isinstance(obj,list):
            for v in obj:walk(v)
    walk(schema)

if __name__=='__main__':
    seen=set()
    for item in ROOTS:fetch(BASE+item,seen)
    print(f'{len(seen)} official schemas cached')
    for item in ROOTS:
        obj=json.loads((CACHE/item).read_text())
        print(item, 'required=',obj.get('required'), 'properties=',list(obj.get('properties',{})))
