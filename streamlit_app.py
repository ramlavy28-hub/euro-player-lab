"""Public-data player comparison lab."""
from dataclasses import asdict
import json
import pandas as pd
import streamlit as st
from demo.engine import ROOT,Settings,aggregate,source_fingerprint,cohort_rows,scores,BASE_METRICS,CUSTOM_METRICS,DEFENSIVE_METRICS
from demo.charts import radar,pitch,comparison_board
from demo.dispersion import describe
import plotly.graph_objects as go
ROLES={'6':'6 · Holding midfielder','8':'8 · Central midfielder','10':'10 · Attacking midfielder','other':'Other positions','GK':'Goalkeeper'}
DEFS={
'op_passes_p90':'Passes without pass.type / minutes × 90; public open-play approximation.',
'passing_pct':'Completed passes / all attempted passes × 100.',
'pressured_pct':'Completed under_pressure passes / attempted under_pressure passes × 100.',
'deep_progressions_p90':'Completed passes and carries from start_x < 80 to end_x ≥ 80, per 90.',
'dribbles_p90':'Dribble events with outcome = Complete, per 90.',
'key_passes_p90':'Completed passes without pass.type linked to a shot, including goals, per 90.',
'box_passes_p90':'Completed passes without pass.type from outside to inside the box, per 90.',
'shots_p90':'Shot attempts in periods 1–4, per 90.',
'pre_key_p90':'First of two completed passes before a shot, using the strict sequence rule, per 90.',
'support_p90':'Completed receptions from pressured passers, pass length ≤10 metres. Progression filter optional.',
'dangerous_losses_total':'Total build-up turnovers followed by an opposition in-box shot. Each loss counts once. Lower totals receive higher radar percentiles; minutes affect exposure.'}
st.set_page_config(page_title='Player lab | EURO 2025',page_icon=':material/sports_soccer:',layout='wide',initial_sidebar_state='collapsed')
st.caption('FOOTBALL RESEARCH  /  EURO 2025')
st.title('Player comparison lab')
@st.cache_data(max_entries=8,show_spinner='Building match sequences and player metrics…')
def load_data(settings,fingerprint,scope):
    return aggregate(Settings(**settings),match_ids=[4020846] if scope=='Final only' else None)
if 'settings' not in st.session_state: st.session_state.settings=asdict(Settings())
if 'saved_examples' not in st.session_state: st.session_state.saved_examples=[]
with st.sidebar:
    st.header('Comparison settings')
    scope=st.selectbox('Match sample',['Full tournament','Final only'],key='scope')
    roles=st.multiselect('Position groups',list(ROLES),default=['6','8','10'],format_func=ROLES.get,key='roles')
    min_minutes=st.slider('Minimum minutes',0,600,120 if scope=='Full tournament' else 30,30,key=f'min_minutes_{scope}')
    min_losses=0  # Total-count metric has no minimum-loss denominator.
    with st.expander('Experimental calculation rules'):
        st.caption('The 10-metre limit and two opposition actions are selected conditions. Other thresholds remain trial rules.')
        with st.form('settings_form'):
            c=st.session_state.settings
            pre=st.slider('Pre-key window (seconds)',3,20,c['pre_window'])
            progression=st.checkbox('Apply experimental progression filter',value=c['progress_min_x'] is not None)
            min_x=st.slider('Minimum X progression (not metres)',0,10,int(c['progress_min_x'] or 5))
            settle_s=st.slider('Minimum build-up duration (seconds)',3,20,c['settle_seconds'])
            settle_p=st.slider('Previous completed build-up passes',1,8,c['settle_passes'])
            control_s=st.slider('Two-action control window (seconds)',3,10,c['control_window'])
            shot_s=st.slider('Shot window after loss (seconds)',5,30,c['shot_window'])
            second_ok=st.checkbox('Require a completed second pass',value=c['second_pass_completed'],help='Additional conservative trial assumption, not a confirmed requirement.')
            both=st.checkbox('Require loss origin and endpoint in first two thirds',value=c['both_loss_locations'],help='Off: use failed-pass endpoint or another loss event location.')
            if st.form_submit_button('Apply rules',type='primary',width='stretch'):
                st.session_state.settings=asdict(Settings(pre_window=pre,progress_min_x=min_x if progression else None,settle_seconds=settle_s,settle_passes=settle_p,control_window=control_s,shot_window=shot_s,second_pass_completed=second_ok,both_loss_locations=both))
if not (ROOT/'research/euro-demo/manifest.json').exists():
    st.error('Run scripts/fetch_euro_demo.py to prepare tournament files.',title='Data unavailable'); st.stop()
data=load_data(st.session_state.settings,source_fingerprint(),scope)
population=cohort_rows(data,tuple(roles),min_minutes)
st.caption(f"Women's EURO · {data['match_count']} matches · {len(population)} eligible players · StatsBomb Open Data")
if not population:
    st.info('Include more position groups or lower the minimum minutes.',title='No players match these filters'); st.stop()
ordered=sorted(population,key=lambda p:p['player']); by_id={p['player_id']:p for p in ordered}; options=list(by_id)
def player_name(pid):
    p=by_id[pid]; return f"{p['player']} · {p['team']}"
with st.container(border=True):
    left,right=st.columns(2)
    with left: selected_id=st.selectbox('Player 1 · Yellow',options,index=options.index(4658) if 4658 in options else 0,format_func=player_name,key='player')
    with right:
        compare_options=[None]+[pid for pid in options if pid!=selected_id]
        compare_id=st.selectbox('Player 2 · Blue',compare_options,index=compare_options.index(15287) if 15287 in compare_options else 0,format_func=lambda pid:'No comparison' if pid is None else player_name(pid),key='compare')
player=by_id[selected_id]; selected=[player]+([by_id[compare_id]] if compare_id is not None else [])
view=st.segmented_control('Workspace',['Radars','Defending','Cohort statistics','Match examples','Methodology','Data & exports'],default='Radars',key='view',label_visibility='collapsed',width='stretch') or 'Radars'
if view=='Radars':
    layout_mode=st.segmented_control('Chart layout',['Compare radars','Updated radar','Reference board'],default='Compare radars',key='radar_layout',label_visibility='collapsed') or 'Compare radars'
    if layout_mode=='Compare radars':
        left,right=st.columns(2,gap='medium')
        with left,st.container(border=True):
            st.subheader('Public baseline'); st.caption('8 metrics · existing football actions')
            st.plotly_chart(radar(selected,population,False,min_losses),width='stretch',theme=None,key='base_radar',alt='Eight-metric baseline comparison radar')
        with right,st.container(border=True):
            st.subheader('Research additions'); st.caption('11 metrics · baseline + 3 research candidates')
            st.plotly_chart(radar(selected,population,True,min_losses),width='stretch',theme=None,key='new_radar',alt='Updated radar with three research candidates')
    elif layout_mode=='Reference board':
        st.plotly_chart(comparison_board(selected,population,min_losses),width='stretch',theme=None,key='comparison_board',alt='Maccabi-inspired comparison board with tables and two radars')
    else:
        st.plotly_chart(radar(selected,population,True,min_losses),width='stretch',theme=None,key='large_radar',alt='Large updated radar')
    st.caption('Percentiles within the selected cohort. NEW = research candidate. N/A = missing inputs or fewer than 3 valid players. Dangerous losses: fewer is better. Radar area is not an overall score.')
    st.subheader('Metrics at a glance')
    rows=[]
    for key,_,name,_ in BASE_METRICS+CUSTOM_METRICS:
        valid=[p for p in population if p[key] is not None]
        row={'Metric':name,'Cohort N':len(valid)}
        for i,p in enumerate(selected,1):
            row[f'P{i} value']=p[key]; row[f'P{i} percentile']=scores(p,population,min_losses)[key]
        rows.append(row)
    frame=pd.DataFrame(rows)
    numeric={c:st.column_config.NumberColumn(c,format='%.2f') for c in frame.columns if c.startswith('P')}
    def percentile_cell(value):
        if pd.isna(value): return 'background-color: #F0F2F6; color: #6B7280'
        color='#E9F2E6' if value>=60 else '#FFF4CA' if value>=40 else '#F8E2DA'
        return f'background-color: {color}; color: #18243B'
    styled=frame.style.map(percentile_cell,subset=[c for c in frame.columns if 'percentile' in c])
    numeric['Metric']=st.column_config.TextColumn('Metric',width='large')
    numeric['Cohort N']=st.column_config.NumberColumn('Cohort N',width='small')
    st.dataframe(styled,hide_index=True,width='stretch',height=460,column_config=numeric,alt='Player values and cohort percentiles for every metric')
    with st.expander('Player exposure & interpretation'):
        st.dataframe(pd.DataFrame([{'Player':p['player'],'Team':p['team'],'Role group':p['role'],'Minutes':round(p['minutes'],1),'Appearances':p['appearances'],'Eligible losses':p['counts'].get('eligible_losses',0)} for p in selected]),hide_index=True,width='stretch',alt='Player minutes, role and loss exposure')
        st.write('Public baseline approximations are not verified club Tableau formulas. Unavailable OBV and model outputs have not been reconstructed. Short receptions measure support volume, not proven progression. Dangerous losses are total counts, not a rate or percentage. Zero means no qualifying observed sequence; it does not prove safety. Compare minutes and involvement.')
    a,b=st.columns(2)
    with a:
        export=comparison_board(selected,population,min_losses) if layout_mode=='Reference board' else radar(selected,population,True,min_losses)
        st.download_button('Export radar · HTML',export.to_html(include_plotlyjs=True),file_name='euro-radar.html',mime='text/html',width='stretch')
    with b:
        if st.button('Save comparison',width='stretch',icon=':material/bookmark:'):
            st.session_state.saved_examples.append({'scope':scope,'players':[p['player'] for p in selected],'cohort_roles':roles,'min_minutes':min_minutes,'min_losses':min_losses,'settings':data['settings'],'metrics':rows})
            st.success('Saved for this session. Download from Data & exports to retain examples.')
elif view=='Defending':
    st.subheader('Defensive profile')
    st.caption('Public-event metrics · per 90 unless stated · no possession adjustment')
    left,right=st.columns([3,2],gap='medium')
    with left,st.container(border=True):
        st.plotly_chart(radar(selected,population,min_losses=0,defensive=True),width='stretch',theme=None,key='defensive_radar',alt='Defensive radar across nine public-event metrics')
    with right:
        st.markdown('**How to read this profile**')
        st.write('Yellow and blue compare the same players and cohort as the attacking view. Higher percentiles mean more actions, except Dribbled Past: fewer is better.')
        st.write('Action volume is not defensive quality. Team possession, role and duel difficulty affect opportunities. These are not the PAdj values shown in the club screenshots.')
        st.write('Successful Interceptions and Successful Ball Recoveries use explicit outcome filters. Aerial Win % is N/A when no aerial contests are observed.')
    defense_rows=[]
    for key,_,name,definition in DEFENSIVE_METRICS:
        row={'Metric':name,'Definition':definition,'Cohort N':sum(p[key] is not None for p in population)}
        for i,p in enumerate(selected,1):
            row[f'P{i} value']=p[key]; row[f'P{i} percentile']=scores(p,population)[key]
        defense_rows.append(row)
    defense_frame=pd.DataFrame(defense_rows)
    config={c:st.column_config.NumberColumn(c,format='%.2f') for c in defense_frame if c.startswith('P')}
    config['Metric']=st.column_config.TextColumn('Metric',width='medium')
    st.dataframe(defense_frame,hide_index=True,width='stretch',height=390,column_config=config,alt='Defensive values, percentiles and exact definitions')
    st.download_button('Export defensive radar · HTML',radar(selected,population,defensive=True).to_html(include_plotlyjs=True),file_name='euro-defensive-radar.html',mime='text/html')
elif view=='Cohort statistics':
    st.subheader('Cohort variance & distribution')
    st.caption(f'{scope} · selected position groups · minimum {min_minutes} minutes · one observation per player')
    all_metrics=BASE_METRICS+CUSTOM_METRICS+DEFENSIVE_METRICS
    metric_lookup={m[0]:m for m in all_metrics}
    metric_key=st.selectbox('Metric',list(metric_lookup),index=list(metric_lookup).index('dangerous_losses_total'),format_func=lambda k:metric_lookup[k][2],key='dispersion_metric')
    values=[p[metric_key] for p in population]
    summary=describe(values)
    a,b,c,d=st.columns(4)
    for card,label in [(a,'N'),(b,'Mean'),(c,'Variance'),(d,'Std. deviation')]:
        value=summary[label]
        card.metric(label,str(value) if label=='N' else f'{value:.4f}' if value is not None else 'N/A',border=True)
    st.caption('Population variance: Σ(value − cohort mean)² / N, ddof = 0. Missing values are excluded; observed zeros are included. Players have equal weight. Variance uses squared metric units; standard deviation uses original units.')
    st.write(metric_lookup[metric_key][3] if metric_key not in DEFS else DEFS[metric_key])
    if metric_key=='dangerous_losses_total':
        st.info('This is variation between player totals, not variation between matches or an estimate of reliability. Minutes and involvement affect totals. Many zeros can produce a small variance without proving safety.')
    valid=[v for v in values if v is not None]
    if valid:
        distribution=go.Figure(go.Histogram(x=valid,marker_color='#4C60B7',nbinsx=20))
        if metric_key=='dangerous_losses_total': distribution.update_traces(xbins={'start':-0.5,'end':max(valid)+0.5,'size':1},autobinx=False)
        distribution.update_layout(height=310,margin={'l':30,'r':20,'t':20,'b':40},bargap=0.12,xaxis_title=metric_lookup[metric_key][2],yaxis_title='Players',paper_bgcolor='white',plot_bgcolor='#F3F5F9')
        st.plotly_chart(distribution,width='stretch',theme=None,alt='Distribution of metric values across the selected player cohort')
    statistics_frame=pd.DataFrame([{'Metric':name,**describe([p[key] for p in population])} for key,_,name,_ in all_metrics])
    st.subheader('All metrics')
    config={k:st.column_config.NumberColumn(k,format='%.4f') for k in ['Mean','Variance','Std. deviation','Minimum','Maximum']}
    config['Metric']=st.column_config.TextColumn('Metric',width='large')
    st.dataframe(statistics_frame,hide_index=True,width='stretch',column_config=config,alt='Population variance, standard deviation and sample size for all twenty metrics')
    st.download_button('Export cohort statistics · CSV',statistics_frame.to_csv(index=False).encode('utf-8-sig'),file_name='euro-cohort-statistics.csv',mime='text/csv')
elif view=='Match examples':
    kind=st.segmented_control('Research metric',['pre','support','loss'],format_func=lambda x:{'pre':'Pre-Key Passes','support':'Short pressure receptions','loss':'Build-up turnovers'}[x],default='pre',key='trace_kind') or 'pre'
    sequences=[s for s in data['traces'][kind] if s['owner']==selected_id]
    if kind=='loss':
        if st.checkbox('Only losses followed by an in-box shot',value=True,key='only_danger'): sequences=[s for s in sequences if s['dangerous']]
    if kind=='support': sequences=[s for s in sequences if s['selected']]
    if not sequences: st.info('No matching sequences. This does not establish an absence of ability.',title='No matching examples')
    else:
        idx=st.selectbox('Match sequence',list(range(len(sequences))),format_func=lambda i:f"{sequences[i]['events'][0]['match']} · Period {sequences[i]['events'][0]['period']} · {sequences[i]['events'][0]['timestamp']} · #{i+1}",key=f'sequence_{kind}_{selected_id}')
        sequence=sequences[idx]
        st.plotly_chart(pitch(sequence),width='stretch',theme=None,alt='Discrete match events with the first team attacking right')
        st.caption('First team attacks right. Opposition coordinates are rotated to the same pitch. Arrows link discrete events, not continuous movement.')
        if kind=='support': st.write(f"Recipient: {sequence['recipient']} · Length: {sequence['length_m']:.3f} m · Progression: {sequence['dx']:.1f} X units")
        if kind=='loss': st.write(f"Previous passes: {sequence['prior_passes']} · Build-up: {sequence['phase_seconds']:.1f} s · In-box shot: {sequence['dangerous']}")
        st.dataframe(pd.DataFrame(sequence['events']),hide_index=True,width='stretch',alt='Event details and source IDs')
        st.link_button('Official source events',f"https://github.com/statsbomb/open-data/blob/master/data/events/{sequence['events'][0]['match_id']}.json")
        st.download_button('Export sequence · JSON',json.dumps(sequence,ensure_ascii=False,indent=2),file_name='euro-sequence.json',mime='application/json')
elif view=='Methodology':
    st.subheader('Definitions & trial rules')
    for key,_,name,definition in BASE_METRICS+CUSTOM_METRICS+DEFENSIVE_METRICS: st.markdown(f'**{name}**  \n{DEFS.get(key,definition)}')
    st.divider()
    st.write('Pre-Key Passes: two completed passes in the same team possession and period. The second links to a shot. Only the key passer’s receipt and carry may intervene; opposition pressure interrupts this strict chain. The window is adjustable.')
    st.write('Short receptions: completed pass, known recipient, under_pressure on the passer, and pass.length × 0.9144 ≤ 10 metres. No minimum progression by default. StatsBomb coordinates are a normalized 120 × 80 map, not metres.')
    st.code('distance_m = pass_data["length"] * 0.9144\nqualifies_distance = distance_m <= 10',language='python')
    st.write('Build-up proxy: minimum duration and completed passes, with no previous final-third entry. Losses in the first two thirds. A trial proxy, not validated Phases of Play classification.')
    st.write('Control requires two consecutive opposition ball actions within the window. Receipt annotations do not count again. Carries require ≥0.5 seconds and ≥1 coordinate-distance unit. Requiring a completed second pass is an additional trial assumption.')
    st.write('Danger ends at a shot originating inside the box: 102 ≤ x ≤ 120, 18 ≤ y ≤ 62 in the shooter’s coordinates. All outcomes count; no xG requirement. Stop at dead balls or two control actions by the original team. The shot window starts at the loss event.')
    st.code('dangerous_losses_total = count_unique_qualifying_losses()\n# Radar percentile is ranked in reverse: fewer losses = higher percentile',language='python')
    st.write('Minutes reconstruct lineups, substitutions, red cards and position changes. Include added time and extra time; exclude shootouts. Role groups are time-weighted provider positions, not video-validated tactical roles. Percentiles use midranks for ties. Missing denominators remain missing. Total dangerous losses have no minimum-loss filter; the selected minimum minutes still applies. At least 3 players are required for percentiles. These are not proven recruitment predictors.')
    st.json(data['settings'])
elif view=='Data & exports':
    st.subheader('Source coverage & saved examples')
    st.write('Public Women’s EURO 2025 events only. A research demonstration, not a club-system connection. Final report and PDF follow example review.')
    st.link_button('StatsBomb Open Data repository','https://github.com/statsbomb/open-data')
    st.dataframe(pd.DataFrame(data['quality']),hide_index=True,width='stretch',alt='Match coverage and excluded events')
    export=[{k:v for k,v in p.items() if k not in {'role_seconds','counts'}} | {f'count_{k}':v for k,v in p['counts'].items()} for p in population]
    st.download_button('Export cohort · CSV',pd.DataFrame(export).to_csv(index=False).encode('utf-8-sig'),file_name='euro-cohort.csv',mime='text/csv')
    st.download_button('Export rules & examples · JSON',json.dumps({'source':'StatsBomb Open Data EURO2025','settings':data['settings'],'scope':scope,'examples':st.session_state.saved_examples},ensure_ascii=False,indent=2),file_name='euro-examples.json',mime='application/json')
    st.caption(f"{len(st.session_state.saved_examples)} examples saved this session. Download to retain them after server shutdown.")
