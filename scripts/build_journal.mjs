import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const payload=JSON.parse(await fs.readFile(path.join(root,'data/interim/journal.json'),'utf8'));
const wb=Workbook.create();
for(const [name,input] of Object.entries(payload)) {
  const width=name==='Analysen'?9:7;
  const rows=input.map(row=>Array.from({length:width},(_,i)=>{
    const value=row[i]??null;
    return value&&typeof value==='object'&&value.date?new Date(value.date+'T00:00:00Z'):value;
  }));
  const sheet=wb.worksheets.add(name);
  sheet.getRangeByIndexes(0,0,rows.length,width).values=rows;
  sheet.showGridLines=false;
  sheet.getRangeByIndexes(0,0,rows.length,width).format.font={name:'Arial',size:10};
  sheet.getRangeByIndexes(0,0,rows.length,width).format.rowHeight=21;
  sheet.getRangeByIndexes(0,0,rows.length,width).format.columnWidth=17;
  sheet.mergeCells(name==='Analysen'?'A1:I1':'A1:G1');
  sheet.mergeCells(name==='Analysen'?'A2:I2':'A2:G2');
  sheet.getRange('A1').format.font={name:'Arial',size:15,bold:true};
  sheet.getRange('A1').format.rowHeight=29;
  sheet.getRange('A2').format.font={name:'Arial',size:10,italic:true,color:'#526579'};
  sheet.getRangeByIndexes(3,0,1,width).format={fill:'#233B57',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:27};
  sheet.getRange('A5:A'+rows.length).setNumberFormat('yyyy-mm-dd');
  sheet.getRangeByIndexes(4,0,rows.length-4,width).format.verticalAlignment='center';
  sheet.getRange('B5:B'+rows.length).format.horizontalAlignment='center';
  if(name==='Analysen') {
    sheet.getRange('C1:C'+rows.length).format.columnWidth=23;
    sheet.getRange('I1:I'+rows.length).format.columnWidth=43;
    sheet.getRange('D5:H'+rows.length).setNumberFormat('0.000');
    sheet.getRange('D5:H'+rows.length).format.horizontalAlignment='right';
  } else {
    sheet.getRange('D1:D'+rows.length).format.columnWidth=27;
    sheet.getRange('G1:G'+rows.length).format.columnWidth=30;
  }
  sheet.freezePanes.freezeRows(4);
}
wb.recalculate();
const out=path.join(root,'data/raw/lab');
await fs.mkdir(out,{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'Laborjournal_ZnNi_L1.xlsx'));
await fs.mkdir(path.join(root,'docs/previews'),{recursive:true});
for(const name of ['Analysen','Dosierung']) {
  const img=await wb.render({sheetName:name,range:name==='Analysen'?'A1:I13':'A1:G13',scale:1.5});
  await fs.writeFile(path.join(root,'docs/previews',name+'.png'),new Uint8Array(await img.arrayBuffer()));
}
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1000})).ndjson);
console.log(path.join(out,'Laborjournal_ZnNi_L1.xlsx'));
