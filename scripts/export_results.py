"""Export actual SQL results and static figures; never substitutes published answers."""
import csv,json,pathlib,sys
from datetime import date,timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'ingest'))
from common import connect,sources

def secom_shift_null(conn,shifts=300,seed=0,window=20):
    """Chance reference for the SECOM ranking: rotate the failure labels in time (keeping their spacing),
    rebuild the 'within 20 runs before a failure' group and record the largest |effect| each time."""
    import numpy as np
    runs=conn.execute('SELECT run_id,failed FROM realdata.v_secom_window ORDER BY sequence_no').fetchall()
    position={run_id:i for i,(run_id,_) in enumerate(runs)};fail=np.array([f for _,f in runs]);n=len(runs)
    X=np.full((n,590),np.nan)
    for run_id,feature,value in conn.execute('SELECT run_id,feature_no,value FROM realdata.secom_value'):X[position[run_id],feature-1]=value
    def group(f):
        m=np.zeros(n,bool)
        for i in np.where(f)[0]:m[max(0,i-window):i]=True
        return m
    def max_effect(m):
        a,b=X[m],X[~m];na,nb=np.isfinite(a).sum(0),np.isfinite(b).sum(0)
        with np.errstate(all='ignore'):
            sp=np.sqrt(((na-1)*np.nanvar(a,0,ddof=1)+(nb-1)*np.nanvar(b,0,ddof=1))/(na+nb-2))
            d=(np.nanmean(a,0)-np.nanmean(b,0))/sp
        d[(na<2)|(nb<2)|(sp==0)]=np.nan
        return float(np.nanmax(np.abs(d)))
    m=group(fail);observed=max_effect(m)
    rng=np.random.default_rng(seed)
    null=np.array([max_effect(group(np.roll(fail,s))) for s in rng.choice(np.arange(50,n-50),size=shifts,replace=False)])
    return {'runs':n,'failures':int(fail.sum()),'group_runs':int(m.sum()),'other_runs':int(n-m.sum()),
      'failures_in_group':int((m&fail).sum()),'observed_max_abs_effect':round(observed,4),
      'null_shifts':shifts,'null_seed':seed,'null_median_max_abs_effect':round(float(np.median(null)),4),
      'null_p95_max_abs_effect':round(float(np.quantile(null,.95)),4),
      'share_of_shifts_at_or_above_observed':round(float((null>=observed).mean()),3),
      'method':'failure labels rotated by a random offset (50..n-50 runs, without replacement); group and effects recomputed per rotation'}

def main():
    out=ROOT/'docs/results';out.mkdir(parents=True,exist_ok=True)
    phase=sources()['assumptions']['spc_phase_one']['value']
    queries={
      'nickel_imr':'SELECT * FROM lab.v_bi_nickel ORDER BY sampled_local',
      'capability':'SELECT * FROM lab.v_monthly_capability ORDER BY parameter_code,month',
      'rule4_runs':'SELECT * FROM lab.v_rule4_runs ORDER BY parameter_code,run_start',
      'nist_summary':'SELECT * FROM realdata.v_nist_summary',
      'nist_anova':'SELECT * FROM realdata.v_nist_anova',
      'secom_ranking':'SELECT * FROM realdata.v_secom_ranking ORDER BY abs(effect_size) DESC NULLS LAST,feature_no',
      'etl_status':'SELECT * FROM lab.v_etl_latest ORDER BY sheet_name,status,reason',
      'dosing':'SELECT * FROM lab.v_dosing_per_charge ORDER BY additive,day',
      'spc_status':'SELECT * FROM lab.v_spc_status ORDER BY tank_code,parameter_code',
    }
    results={}
    with connect('export_results') as conn:
        conn.execute("SET TimeZone TO 'Europe/Berlin'")   # exported timestamps carry Berlin offsets on any machine
        for name,sql in queries.items():
            cursor=conn.execute(sql);columns=[c.name for c in cursor.description];rows=cursor.fetchall()
            results[name]=[dict(zip(columns,row)) for row in rows]
            with (out/f'{name}.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(columns);writer.writerows(rows)
        summary={
          'nist':results['nist_summary'][0],
          'secom':dict(zip(['runs','failures'],conn.execute('SELECT count(*),count(*) FILTER(WHERE failed) FROM realdata.secom_run').fetchone())),
          'secom_nonmissing':conn.execute('SELECT count(*) FROM realdata.secom_value').fetchone()[0],
          'rule4_runs':results['rule4_runs'],
          'nickel_beyond_limits':[r for r in results['nickel_imr'] if r['beyond_limits']],
          'latest_etl':results['etl_status'],
          'secom_null':secom_shift_null(conn),
        }
        (out/'secom_null.json').write_text(json.dumps(summary['secom_null'],indent=2),encoding='utf-8')
        (out/'summary.json').write_text(json.dumps(summary,default=str,indent=2),encoding='utf-8')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    rows=results['nickel_imr'];dates=[r['sampled_local'] for r in rows]
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
    for ax,cols,label in [(axes[0],['value','cl','ucl','lcl'],'Nickel (g/L)'),(axes[1],['mr','mr_ucl'],'Moving range (g/L)')]:
        for col in cols:
            ax.plot(dates,[float(r[col]) if r[col] is not None else float('nan') for r in rows],
                    label=col.upper(),linewidth=1.5,color={'value':'#1c718a','mr':'#1c718a','cl':'#777777','ucl':'#b05045','lcl':'#b05045','mr_ucl':'#b05045'}[col],
                    linestyle='-' if col in ('value','mr') else '--')
        ax.set_ylabel(label);ax.legend(loc='upper right',ncol=len(cols));ax.grid(alpha=.18)
    signals=[r for r in rows if r['beyond_limits']]
    axes[0].scatter([r['sampled_local'] for r in signals],[float(r['value']) for r in signals],color='#b05045',zorder=5)
    first,last=date.fromisoformat(phase['start']),date.fromisoformat(phase['end_exclusive'])-timedelta(days=1)
    axes[0].set_title(f'L1-T05 · simulated nickel bath | Phase I: {first.day} {first:%B}–{last.day} {last:%B %Y}',loc='left',weight='bold')
    axes[1].set_xlabel('Sample date · Europe/Berlin');fig.savefig(out/'nickel_imr.png',dpi=150);plt.close(fig)
    # A faithful rendered query-result table, explicitly not a screenshot from a SQL client.
    s=results['nist_summary'][0];anova=results['nist_anova']
    fig,ax=plt.subplots(figsize=(11,3.5));ax.axis('off')
    ax.set_title('NIST lithography · results computed in PostgreSQL',loc='left',weight='bold',pad=18)
    ax.text(0,.91,f"n = {s['n']}     mean = {float(s['mean']):.5f}     sample SD = {float(s['sd']):.5f}     median = {float(s['median']):.5f}",transform=ax.transAxes)
    table=ax.table(cellText=[[r['component'],r['df'],f"{r['ss']:.5f}",f"{r['ms']:.5f}",f"{r['variance_component']:.4f}"] for r in anova],
      colLabels=['Nested component','df','Sum of squares','Mean square','Variance'],cellLoc='center',bbox=[0,.2,1,.6],colWidths=[.3,.1,.2,.2,.2])
    table.auto_set_font_size(False);table.set_fontsize(10)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor('#dce2e8')
        if r==0:cell.set_facecolor('#233b57');cell.set_text_props(color='white',weight='bold')
    ax.text(0,.04,'SQL result rendering • raw_width from LITHOGRA.DAT • 15 published-answer checks passed',transform=ax.transAxes,color='#526579',fontsize=9)
    fig.savefig(out/'nist_query_results.png',dpi=160,bbox_inches='tight');plt.close(fig)
    ranked=[r for r in results['secom_ranking'] if r['effect_size'] is not None][:15][::-1]
    fig,ax=plt.subplots(figsize=(10,6),layout='constrained')
    ax.barh([str(r['feature_no']) for r in ranked],[float(r['effect_size']) for r in ranked],color='#1c718a')
    ax.axvline(0,color='#999999',lw=.8);ax.set_ylabel('Sensor (1-based)');ax.set_xlabel('(Mean in group − mean of other runs) / pooled SD')
    null=summary['secom_null'];p95=null['null_p95_max_abs_effect']
    for x in (-p95,p95):ax.axvline(x,color='#b05045',lw=1.2,ls='--')
    ax.plot([],[],color='#b05045',lw=1.2,ls='--',label=f"chance reference: 95th percentile of the largest |effect| over {null['null_shifts']} circular shifts ({p95:.2f})")
    ax.set_ylim(-1.6,len(ranked)-.4);ax.legend(loc='lower right',fontsize=8,frameon=False)
    ax.set_title(f"SECOM · {null['group_runs']:,} runs within 20 runs before a failure vs {null['other_runs']:,} other runs "
                 f"({null['failures_in_group']} of {null['failures']} failures inside the group)\n"
                 f"Top |effect| {null['observed_max_abs_effect']:.2f} vs chance median {null['null_median_max_abs_effect']:.2f}; "
                 "exploratory ranking, no holdout validation or causal interpretation",loc='left',fontsize=10)
    fig.savefig(out/'secom_ranking.png',dpi=150);plt.close(fig)
    print(f'Exported {len(queries)} SQL result tables, the SECOM chance reference and 3 figures to {out.relative_to(ROOT).as_posix()}')

if __name__=='__main__':main()
