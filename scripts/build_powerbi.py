"""Generate an inspectable PBIP, PBIR visuals and an import-mode PostgreSQL model."""
import json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'ingest'))
from common import connect
BASE='https://developer.microsoft.com/json-schemas/'
OUT=ROOT/'powerbi'

def write(path,obj):
    p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,indent=2),encoding='utf-8')

def schema(part):return BASE+part+'/schema.json'
def column(entity,name):return {'Column':{'Expression':{'SourceRef':{'Entity':entity}},'Property':name}}
def projection(entity,name,aggregate=False):
    field=column(entity,name)
    if aggregate:field={'Aggregation':{'Expression':field,'Function':1}} # average
    return {'field':field,'queryRef':f'Avg({entity}.{name})' if aggregate else f'{entity}.{name}','nativeQueryRef':name}

def literal(value):return {'expr':{'Literal':{'Value':value}}}

def visual(page,name,entity,kind,fields,x,y,w,h,category=None,objects=None):
    state={'Category':{'projections':[projection(entity,category)]},'Y':{'projections':[projection(entity,f,True) for f in fields]}} if category else {'Values':{'projections':[projection(entity,f) for f in fields]}}
    body={'visualType':kind,'query':{'queryState':state},'drillFilterOtherVisuals':True}
    if objects:body['objects']=objects
    write(pathlib.Path(f'BathLab.Report/definition/pages/{page}/visuals/{name}/visual.json'),{
      '$schema':schema('fabric/item/report/definition/visualContainer/1.0.0'),'name':name,
      'position':{'x':x,'y':y,'z':0,'height':h,'width':w,'tabOrder':0},
      'visual':body})

def main():
    write(pathlib.Path('BathLab.pbip'),{'$schema':schema('fabric/pbip/pbipProperties/1.0.0'),'version':'1.0','artifacts':[{'report':{'path':'BathLab.Report'}}],'settings':{'enableAutoRecovery':True}})
    write(pathlib.Path('BathLab.Report/definition.pbir'),{'$schema':schema('fabric/item/report/definitionProperties/2.0.0'),'version':'4.0','datasetReference':{'byPath':{'path':'../BathLab.SemanticModel'}}})
    write(pathlib.Path('BathLab.SemanticModel/definition.pbism'),{'$schema':schema('fabric/item/semanticModel/definitionProperties/1.0.0'),'version':'1.0','settings':{'qnaEnabled':False}})
    write(pathlib.Path('BathLab.Report/definition/version.json'),{'$schema':schema('fabric/item/report/definition/versionMetadata/1.0.0'),'version':'2.0.0'})
    write(pathlib.Path('BathLab.Report/definition/report.json'),{'$schema':schema('fabric/item/report/definition/report/1.0.0'),'themeCollection':{},'layoutOptimization':'None'})
    pages=[('TankL1T05','L1-T05 · simulated bath'),('NIST','NIST · real reference'),('SECOM','SECOM · exploratory')]
    write(pathlib.Path('BathLab.Report/definition/pages/pages.json'),{'$schema':schema('fabric/item/report/definition/pagesMetadata/1.0.0'),'pageOrder':[p[0] for p in pages],'activePageName':'TankL1T05'})
    for name,label in pages:
        write(pathlib.Path(f'BathLab.Report/definition/pages/{name}/page.json'),{'$schema':schema('fabric/item/report/definition/page/1.0.0'),'name':name,'displayName':label,'displayOption':'FitToPage','height':900,'width':1440})
    # signal_value is only filled at individuals-limit breaches and Rule 4 signals: drawn as markers without a line.
    visual('TankL1T05','Nickel','Nickel','lineChart',['value','cl','ucl','lcl','signal_value'],20,20,900,350,'sampled_local',
      {'lineStyles':[{'properties':{'showMarker':literal('true'),'strokeWidth':literal('0L')},'selector':{'metadata':'Avg(Nickel.signal_value)'}}]})
    visual('TankL1T05','MovingRange','Nickel','lineChart',['mr','mr_ucl'],20,390,900,300,'sampled_local')
    visual('TankL1T05','Capability','Capability','tableEx',['parameter_code','month','n','cpk','ppk','small_sample','interpretation'],940,20,480,480)
    visual('TankL1T05','ETL','ETL','tableEx',['file_name','sheet_name','status','reason','rows'],940,520,480,360)
    visual('TankL1T05','Dosing','Dosing','tableEx',['day','additive','ml_per_kah','status'],20,710,900,170)
    visual('NIST','Summary','NISTSummary','tableEx',['n','mean','sd','median','minimum','maximum'],20,20,1380,250)
    visual('NIST','ANOVA','NISTAnova','tableEx',['component','df','ss','ms','variance_component'],20,300,1380,400)
    visual('SECOM','Ranking','SECOM','tableEx',['feature_no','n_before','n_other','effect_size','status'],20,20,1380,850)
    mappings={'Nickel':('lab','v_bi_nickel'),'Capability':('lab','v_bi_capability'),'ETL':('lab','v_etl_latest'),'Dosing':('lab','v_dosing_per_charge'),'NISTSummary':('realdata','v_nist_summary'),'NISTAnova':('realdata','v_nist_anova'),'SECOM':('realdata','v_secom_ranking')}
    tables=[]
    with connect('powerbi_metadata') as conn:
        for name,(ns,view) in mappings.items():
            cols=conn.execute('SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(ns,view)).fetchall()
            assert cols,f'Missing database view {ns}.{view}'
            def dtype(t):return 'int64' if t in ('bigint','integer','smallint') else 'double' if t in ('numeric','double precision','real') else 'dateTime' if t in ('date','timestamp without time zone') else 'boolean' if t=='boolean' else 'string'
            tables.append({'name':name,'columns':[{'name':c,'dataType':dtype(t),'sourceColumn':c,'summarizeBy':'none'} for c,t in cols],
              'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':[
              'let','    Source = PostgreSQL.Database(Server, Database, [CreateNavigationProperties=false]),',
              f'    Data = Source{{[Schema="{ns}",Item="{view}"]}}[Data]','in','    Data']}}]})
    model={'name':'BathLab','compatibilityLevel':1567,'model':{'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3',
      'expressions':[{'name':'Server','kind':'m','expression':'"127.0.0.1:55433" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'},
                     {'name':'Database','kind':'m','expression':'"bath_lab_spc" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
      'tables':tables,'annotations':[{'name':'PBI_QueryOrder','value':json.dumps(list(mappings))}]}}
    write(pathlib.Path('BathLab.SemanticModel/model.bim'),model)
    print('Power BI: 3 pages, 8 visuals, 7 PostgreSQL views; no embedded credentials.')

if __name__=='__main__':main()
