"""Validate PBIR against cached official Microsoft schemas (does not emulate Desktop)."""
import json,pathlib
from jsonschema import Draft7Validator,RefResolver
ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    store={}
    for path in (ROOT/'.local/pbir-schemas').rglob('schema.json'):
        value=json.loads(path.read_text(encoding='utf-8'));store[value['$id']]=value
    if not store:raise SystemExit('Run scripts/fetch_powerbi_schemas.py first.')
    checked=[];errors=[]
    for path in (ROOT/'powerbi').rglob('*'):
        if not path.is_file() or path.suffix not in ('.json','.pbip','.pbir','.pbism'):continue
        value=json.loads(path.read_text(encoding='utf-8'));uri=value.get('$schema')
        if not uri:continue
        definition=store[uri]
        validator=Draft7Validator(definition,resolver=RefResolver(uri,definition,store=store))
        for error in validator.iter_errors(value):errors.append(f'{path.relative_to(ROOT)}: {list(error.path)}: {error.message}')
        checked.append(str(path.relative_to(ROOT)))
    report={'validated_files':checked,'errors':errors,'desktop_refresh_verified':False,
            'limitation':'JSON schemas validate PBIP/PBIR structure, not semantic-model engine compatibility or rendered visuals.'}
    (ROOT/'docs/results/powerbi_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));assert not errors

if __name__=='__main__':main()
