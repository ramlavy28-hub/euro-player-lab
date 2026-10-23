"""Plotly radar and auditable pitch diagrams for the local demo."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from demo.engine import scores, BASE_METRICS, CUSTOM_METRICS, DEFENSIVE_METRICS

COLORS = ['#D9BC19', '#4C60B7']
FILLS = ['rgba(239,212,58,0.56)', 'rgba(83,101,192,0.52)']
BLUE = '#40589E'
YELLOW = '#EFDB59'

def _radar_traces(players,population,metrics,min_losses):
    theta=[i*360/len(metrics) for i in range(len(metrics))]
    traces=[]
    # Concentric filled disks reproduce alternating grey bands; no score is filled in.
    circle=list(range(0,361,3))
    for radius in range(100,0,-10):
        color='#D0D0D0' if radius%20==0 else '#FFFFFF'
        traces.append(go.Scatterpolar(r=[radius]*len(circle),theta=circle,mode='lines',line={'width':0,'color':color},fill='toself',fillcolor=color,hoverinfo='skip',showlegend=False))
    for i,p in enumerate(players):
        ranks=scores(p,population,min_losses)
        r=[ranks[m[0]] for m in metrics]
        customdata=[[f"{p[m[0]]:.2f}" if p[m[0]] is not None else 'N/A',m[2]] for m in metrics]
        traces.append(go.Scatterpolar(r=r+r[:1],theta=theta+theta[:1],name=p['player'],legendgroup=str(p['player_id']),mode='lines+markers',connectgaps=False,
            fill='toself' if all(v is not None for v in r) else None,fillcolor=FILLS[i%2],line={'color':COLORS[i%2],'width':1.7},marker={'size':3.5},customdata=customdata+customdata[:1],
            hovertemplate='%{customdata[1]}<br>Value: %{customdata[0]}<br>Percentile: %{r:.1f}<extra>%{fullData.name}</extra>'))
    groups=(['Tackling','Pressure','Pressure','Pressure','Regaining','Regaining','Aerial','Aerial','Duels'] if metrics==DEFENSIVE_METRICS else ['Passing','Passing','Passing','Progression','Dribbling','Creating','Creating','Shooting']+(['Research','Research','Research'] if len(metrics)>8 else []))
    step=360/len(metrics)
    starts=[i for i in range(len(groups)) if groups[i]!=groups[i-1]]
    for i in starts:
        angle=(i-0.5)*step
        traces.append(go.Scatterpolar(r=[0,100],theta=[angle,angle],mode='lines',line={'color':'#1A1A1A','width':3.2},hoverinfo='skip',showlegend=False))
    return traces

def _polar_style(metrics):
    labels={
        'Open Play Passes /90':'OP Passes /90',
        'Pressured Pass %':'Pressured<br>Pass %',
        'Deep Progressions':'Deep<br>Prog.',
        'Successful Dribbles /90':'Dribbles /90',
        'Open Play Key Passes /90':'Key Passes /90',
        'OP Passes Into Box /90':'Box Passes<br>/90',
        'NEW · Pre-Key Passes /90':'NEW · Pre-Key<br>/90',
        'NEW · Short Receipts /90':'NEW · Receipts<br>/90',
        'NEW · Build-Up Safety %':'NEW · Safety %',
    }
    ticks=[m[1].replace('<br>',' ').replace('Pressure Receipts /90','Receipts /90').replace('Progressions /90','Progressions') for m in metrics]
    ticks=[labels.get(label,label) for label in ticks]
    return {'bgcolor':'#FFFFFF','radialaxis':{'range':[0,100],'tickvals':list(range(10,101,10)),'angle':90,'gridcolor':'rgba(0,0,0,0)','linecolor':'rgba(0,0,0,0)','tickfont':{'size':8,'color':'#5F5F5F'}},
            'angularaxis':{'type':'linear','tickmode':'array','tickvals':[i*360/len(metrics) for i in range(len(metrics))],'ticktext':ticks,'direction':'clockwise','rotation':90,'gridcolor':'rgba(0,0,0,0)','linecolor':'#E0E0E0','tickfont':{'size':10,'color':'#111111'}}}

def radar(players, population, updated=True, min_losses=5, defensive=False):
    metrics = DEFENSIVE_METRICS if defensive else BASE_METRICS + (CUSTOM_METRICS if updated else [])
    fig = go.Figure()
    for trace in _radar_traces(players,population,metrics,min_losses): fig.add_trace(trace)
    fig.update_layout(height=440, margin={'t':45,'b':75,'l':85,'r':85},
        paper_bgcolor='#FFFFFF', font={'family':'Arial', 'size':11, 'color':'#111111'},
        polar=_polar_style(metrics),
        legend={'orientation':'h', 'y':-0.20,'x':0.5,'xanchor':'center','font':{'size':10}})
    return fig

def _rank_color(value):
    if value is None: return '#EEEEEE'
    return '#C53532' if value<20 else '#E57558' if value<40 else '#F0D66A' if value<60 else '#90B779' if value<80 else '#508A54'

def comparison_board(players,population,min_losses=5):
    """Single framed dashboard matching the supplied club reference structure."""
    fig=make_subplots(rows=2,cols=3,specs=[[{'type':'table'},{'type':'polar','rowspan':2},{'type':'polar','rowspan':2}],[{'type':'table'},None,None]],column_widths=[0.29,0.355,0.355],row_heights=[0.34,0.66],horizontal_spacing=0.012,vertical_spacing=0.015)
    one=players[0]; two=players[1] if len(players)>1 else None
    info=[('Player name','player'),('Team','team'),('Role group','role'),('Minutes played','minutes'),('Appearances','appearances')]
    values=[[name for name,_ in info],[],[]]
    for p,col in [(one,1),(two,2)]:
        for _,key in info:
            val=p.get(key) if p else None
            values[col].append(f'{val:.1f}' if isinstance(val,float) else str(val) if val is not None else 'N/A')
    fig.add_trace(go.Table(columnwidth=[95,105,105],header={'values':['<b>Information Table</b>','<b>Player 1</b>','<b>Player 2</b>'],'fill_color':YELLOW,'line_color':BLUE,'font':{'color':BLUE,'size':10},'height':24},cells={'values':values,'fill_color':'white','line_color':'#A9A9A9','align':['left','center','center'],'font':{'size':9,'color':'#222222'},'height':24}),row=1,col=1)
    metrics=BASE_METRICS+CUSTOM_METRICS
    cols=[[],[],[],[],[]]; fills=[[],[],[],[],[]]
    for j,(key,_,name,_) in enumerate(metrics):
        if j==len(BASE_METRICS):
            for col in range(5): cols[col].append('<b>Research additions</b>' if col==0 else ''); fills[col].append(YELLOW)
        display={'support_p90':'Short pressure<br>receipts /90'}.get(key,name)
        cols[0].append(('<b>NEW · </b>' if j>=len(BASE_METRICS) else '')+display)
        fills[0].append('#FFF8DB' if j>=len(BASE_METRICS) else '#FFFFFF')
        for p,offset in [(one,1),(two,3)]:
            value=p[key] if p else None; rank=scores(p,population,min_losses)[key] if p else None
            cols[offset].append(f'{value:.2f}' if value is not None else 'N/A'); fills[offset].append('#FFFFFF')
            cols[offset+1].append(str(round(rank)) if rank is not None else 'N/A'); fills[offset+1].append(_rank_color(rank))
    for label,count in [('Eligible build-up losses','eligible_losses')]:
        cols[0].append(label); fills[0].append('#F4F4F4')
        for p,offset in [(one,1),(two,3)]:
            cols[offset].append(str(p['counts'].get(count,0)) if p else 'N/A'); fills[offset].append('#FFFFFF')
            cols[offset+1].append(''); fills[offset+1].append('#FFFFFF')
    fig.add_trace(go.Table(columnwidth=[145,45,38,45,38],header={'values':['<b>Metric</b>','<b>V1</b>','<b>Pctl</b>','<b>V2</b>','<b>Pctl</b>'],'fill_color':YELLOW,'line_color':BLUE,'font':{'color':BLUE,'size':10},'height':22},cells={'values':cols,'fill_color':fills,'line_color':'#AEAEAE','align':['left','center','center','center','center'],'font':{'size':9,'color':'#202020'},'height':23}),row=2,col=1)
    for col,metrics in [(2,BASE_METRICS),(3,BASE_METRICS+CUSTOM_METRICS)]:
        for trace in _radar_traces(players,population,metrics,min_losses):
            if col==3: trace.showlegend=False
            fig.add_trace(trace,row=1,col=col)
    for name,metrics in [('polar',BASE_METRICS),('polar2',BASE_METRICS+CUSTOM_METRICS)]:
        fig.layout[name].update(**_polar_style(metrics))
        fig.layout[name].domain.y=[0.24,0.87]
        x0,x1=fig.layout[name].domain.x
        fig.layout[name].domain.x=[x0+0.065,x1-0.065]
    boundaries=[(0,0.282),(0.294,0.641),(0.653,1)]
    titles=['Midfielder Comparison','Public baseline','With research additions']
    for (x0,x1),title in zip(boundaries,titles):
        fig.add_shape(type='rect',x0=x0,x1=x1,y0=0,y1=1.035,xref='paper',yref='paper',line={'color':BLUE,'width':1.7},fillcolor='rgba(0,0,0,0)')
        fig.add_shape(type='rect',x0=x0,x1=x1,y0=1,y1=1.035,xref='paper',yref='paper',line={'color':BLUE,'width':1.5},fillcolor=YELLOW)
        fig.add_annotation(x=(x0+x1)/2,y=1.018,xref='paper',yref='paper',text=f'<b>{title}</b>',showarrow=False,font={'size':14,'color':BLUE},xanchor='center',yanchor='middle')
    fig.add_annotation(x=0.647,y=0.13,xref='paper',yref='paper',text='Yellow: Player 1 · Blue: Player 2<br>NEW = research metric · N/A = insufficient exposure',showarrow=False,font={'size':11,'color':'#444444'})
    fig.update_layout(height=640,margin={'l':8,'r':8,'t':40,'b':45},paper_bgcolor='#FFFFFF',font={'family':'Arial','color':'#111111'},legend={'orientation':'h','x':0.65,'xanchor':'center','y':0.04})
    return fig

def pitch(sequence):
    fig = go.Figure(); shapes = []
    def line(x0,y0,x1,y1): shapes.append({'type':'line','x0':x0,'y0':y0,'x1':x1,'y1':y1,'line':{'color':'#B9C9BA','width':1}})
    for a in [(0,0,120,0),(0,80,120,80),(0,0,0,80),(120,0,120,80),(60,0,60,80)]: line(*a)
    for x0,x1 in [(0,18),(102,120)]:
        for a in [(x0,18,x1,18),(x0,62,x1,62),(18 if x0==0 else 102,18,18 if x0==0 else 102,62)]: line(*a)
    shapes.append({'type':'circle','x0':50,'y0':30,'x1':70,'y1':50,'line':{'color':'#B9C9BA','width':1}})
    ref = sequence['events'][0]['team_id']
    def coords(loc, tid):
        return loc[:2] if tid==ref else [120-loc[0],80-loc[1]]
    for i,e in enumerate(sequence['events']):
        if not e['location']: continue
        x,y=coords(e['location'],e['team_id']); color=COLORS[0] if e['team_id']==ref else COLORS[1]
        fig.add_trace(go.Scatter(x=[x],y=[y],mode='markers+text',text=[str(i+1)],textposition='top center',marker={'size':12,'color':color},name=f"{i+1}. {e['type']}",customdata=[[e['player'],e['timestamp']]],hovertemplate='%{customdata[0]}<br>%{customdata[1]}<extra>%{fullData.name}</extra>'))
        if e.get('end_location'):
            ex,ey=coords(e['end_location'],e['team_id'])
            fig.add_annotation(x=ex,y=ey,ax=x,ay=y,xref='x',yref='y',axref='x',ayref='y',showarrow=True,arrowhead=3,arrowwidth=2,arrowcolor=color)
    fig.update_layout(shapes=shapes,height=430,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='#F1F6EF',font={'family':'Arial','size':11},margin={'l':15,'r':15,'t':20,'b':40},xaxis={'range':[-2,122],'visible':False},yaxis={'range':[82,-2],'visible':False,'scaleanchor':'x','scaleratio':1},legend={'orientation':'h','y':-0.05})
    return fig

