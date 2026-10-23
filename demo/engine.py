"""Auditable offline demo engine. Explicit approximations, not club formulas."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import gzip
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from calculate_candidate_pilot import calculate, clock, complete, loss_candidate, pass_length_metres, typ, team

DATA = ROOT/'research/euro-demo'
STOP = {'Half End', 'Foul Committed', 'Foul Won', 'Offside', 'Injury Stoppage', 'Referee Ball-Drop'}
ROLE_NAMES = {'6': '6 · קשר אחורי', '8': '8 · קשר מרכזי', '10': '10 · קשר התקפי', 'other': 'עמדות אחרות', 'GK': 'שוערת'}
BASE_METRICS = [
    ('op_passes_p90', 'Open Play<br>Passes /90', 'Open Play Passes /90', 'מסירות ללא pass.type, חלקי דקות כפול90; קירוב ציבורי למסירות משחק פתוח'),
    ('passing_pct', 'Passing %', 'Passing%', 'מסירות מוצלחות מכל הסוגים / כלל ניסיונות המסירה ×100'),
    ('pressured_pct', 'Pressured<br>Pass %', 'Pressured Pass%', 'מסירות מוצלחות עם under_pressure / כל ניסיונות המסירה עם under_pressure ×100'),
    ('deep_progressions_p90', 'Deep<br>Progressions /90', 'Deep Progressions /90', 'מסירות מוצלחות ונשיאות עם start_x<80 ו־end_x≥80, ל־90'),
    ('dribbles_p90', 'Successful<br>Dribbles /90', 'Successful Dribbles /90', 'Dribble עם outcome=Complete, ל־90'),
    ('key_passes_p90', 'Open Play<br>Key Passes /90', 'Open Play Key Passes /90', 'מסירות מוצלחות ללא pass.type עם קישור לבעיטה, כולל מסירות לשער, ל־90'),
    ('box_passes_p90', 'OP Passes<br>Into Box /90', 'OP Passes Into Box /90', 'מסירות מוצלחות ללא pass.type שמתחילות מחוץ לרחבה ומסתיימות בה, ל־90'),
    ('shots_p90', 'Shots /90', 'Shots /90', 'כל ניסיונות הבעיטה בתקופות1–4, ל־90'),
]
CUSTOM_METRICS = [
    ('pre_key_p90', 'NEW · Pre-Key<br>Passes /90', 'Pre-Key Passes /90', 'שתי מסירות מוצלחות לפני בעיטה לפי כלל הרצף המחמיר, ל־90'),
    ('support_p90', 'NEW · Short<br>Pressure Receipts /90', 'Short Receptions from Pressured Passers /90', 'קבלות מוצלחות ממוסר תחת לחץ באורך עד10מטר; סינון קידום אופציונלי וניסיוני'),
    ('dangerous_losses_total', 'NEW · Dangerous<br>Losses ↓', 'Build-Up Losses Leading to In-Box Shots', 'Total qualifying build-up turnovers followed by an opposition in-box shot. Lower is better.'),
]
DEFENSIVE_METRICS = [
    ('tackles_p90','Tackles /90','Tackles /90','All Duel events of type Tackle, all outcomes, per 90. No possession adjustment.'),
    ('pressures_p90','Pressures /90','Pressures /90','Pressure events per 90. No possession adjustment.'),
    ('opp_half_pressures_p90','Opp. Half<br>Pressures /90','Opposition-Half Pressures /90','Pressure events with location x >= 60, per 90.'),
    ('counterpressures_p90','Counterpressures<br>/90','Counterpressures /90','Pressure events with counterpress = true, per 90.'),
    ('interceptions_p90','Interceptions<br>/90','Successful Interceptions /90','Interception outcomes Won, Success In Play or Success Out, per 90.'),
    ('recoveries_p90','Recoveries /90','Successful Ball Recoveries /90','Ball Recovery events without recovery_failure, per 90.'),
    ('aerial_wins_p90','Aerial Wins /90','Aerial Wins /90','Events with aerial_won on pass, shot, miscontrol or clearance, counted once per event, per 90.'),
    ('aerial_win_pct','Aerial Win %','Aerial Win %','Aerial wins / (aerial wins + Duel Aerial Lost) × 100. Missing without aerial contests.'),
    ('dribbled_past_p90','Dribbled Past<br>/90 ↓','Dribbled Past /90','Dribbled Past events per 90. Lower is better; opportunity and difficulty are not adjusted.'),
]
LOWER_IS_BETTER = {'dangerous_losses_total','dribbled_past_p90'}

def defensive_counts(e):
    """Explicit public-event definitions; not commercial PAdj reconstruction."""
    t=typ(e); duel=e.get('duel',{}); location=e.get('location')
    return {
        'tackles':int(t=='Duel' and duel.get('type',{}).get('name')=='Tackle'),
        'pressures':int(t=='Pressure'),
        'opp_half_pressures':int(t=='Pressure' and bool(location) and location[0]>=60),
        'counterpressures':int(t=='Pressure' and bool(e.get('counterpress'))),
        'interceptions':int(t=='Interception' and e.get('interception',{}).get('outcome',{}).get('name') in {'Won','Success In Play','Success Out'}),
        'recoveries':int(t=='Ball Recovery' and not e.get('ball_recovery',{}).get('recovery_failure')),
        'aerial_wins':int(any(e.get(k,{}).get('aerial_won',False) for k in ('pass','shot','miscontrol','clearance'))),
        'aerial_losses':int(t=='Duel' and duel.get('type',{}).get('name')=='Aerial Lost'),
        'dribbled_past':int(t=='Dribbled Past'),
    }

@dataclass(frozen=True)
class Settings:
    pre_window: int = 10
    progress_min_x: float | None = None
    settle_seconds: int = 8
    settle_passes: int = 3
    control_window: int = 5
    shot_window: int = 15
    second_pass_completed: bool = True
    both_loss_locations: bool = False
    min_carry_duration: float = 0.5
    min_carry_units: float = 1.0

def role(position_id):
    if position_id in {9, 10, 11}: return '6'
    if position_id in {13, 14, 15}: return '8'
    if position_id in {18, 19, 20}: return '10'
    return 'GK' if position_id == 1 else 'other'

def in_box(location):
    return bool(location and len(location) >= 2 and 102 <= location[0] <= 120 and 18 <= location[1] <= 62)

def read_matches():
    return json.loads((ROOT/'research/womens-euro-sample/raw/matches/53/315.json').read_text(encoding='utf-8'))

def match_label(match):
    return f"{match['match_date']} · {match['home_team']['home_team_name']} – {match['away_team']['away_team_name']}"

def stoppage(e):
    # Advantage is not a dead ball. Original pilot stopped at every foul.
    if typ(e) in {'Foul Committed', 'Foul Won'}:
        return not e.get('foul_committed', e.get('foul_won', {})).get('advantage')
    return typ(e) in STOP or bool(e.get('out'))

def meaningful_carry(e, cfg):
    a, b = e.get('location'), e.get('carry', {}).get('end_location')
    return bool(a and b and e.get('duration', 0) >= cfg.min_carry_duration and math.dist(a[:2], b[:2]) >= cfg.min_carry_units)

def is_ball_action(e, cfg):
    t = typ(e)
    if t == 'Carry': return meaningful_carry(e, cfg)
    if t == 'Goal Keeper':
        return e.get('goalkeeper', {}).get('type', {}).get('name') in {'Collected', 'Keeper Sweeper', 'Smother'}
    # Receipt annotations and mirrored tackle/dispossessed duels are not extra actions.
    return t in {'Pass', 'Shot', 'Ball Recovery', 'Dribble', 'Miscontrol', 'Dispossessed', 'Interception'}

def controls_ball(e, cfg, second=False):
    t = typ(e)
    if t == 'Pass': return complete(e) if second and cfg.second_pass_completed else True
    if t == 'Ball Recovery': return not e.get('ball_recovery', {}).get('recovery_failure')
    if t == 'Dribble': return e.get('dribble', {}).get('outcome', {}).get('name') == 'Complete'
    if t == 'Interception': return e.get('interception', {}).get('outcome', {}).get('name') in {'Won', 'Success', 'Success In Play'}
    return t in {'Carry', 'Shot', 'Goal Keeper'}

def summary(e, match):
    return {'id': e['id'], 'index': e['index'], 'period': e['period'], 'timestamp': e['timestamp'],
            'minute': e.get('minute'), 'type': typ(e), 'player_id': e.get('player', {}).get('id'),
            'player': e.get('player', {}).get('name'), 'team_id': team(e),
            'team': e.get('team', {}).get('name'), 'location': e.get('location'),
            'end_location': e.get('pass', e.get('carry', {})).get('end_location'),
            'match_id': match['match_id'], 'match': match_label(match)}

def playing_time(events):
    """Elapsed on-pitch seconds including stoppage/extra time; excludes shootout.

    Use actual period end clocks, substitutions, red cards, tactical and event positions.
    Role labels are positional proxies, not independently reviewed tactical roles.
    """
    ends = {p: max(clock(e) for e in events if e['period'] == p) for p in sorted({e['period'] for e in events})}
    offsets, elapsed = {}, 0
    for p in sorted(ends): offsets[p] = elapsed; elapsed += ends[p]
    profiles, active = {}, {}
    def ensure(pid, name, tid, tname):
        if pid not in profiles:
            profiles[pid] = {'player_id': pid, 'player': name, 'team_id': tid, 'team': tname, 'seconds': 0, 'role_seconds': Counter()}
    def close(pid, now):
        if pid not in active: return
        start, pos = active.pop(pid)
        seconds = max(0, now-start)
        profiles[pid]['seconds'] += seconds
        profiles[pid]['role_seconds'][role(pos)] += seconds
    for i, e in enumerate(events):
        now = offsets[e['period']] + clock(e)
        if typ(e) == 'Starting XI':
            for item in e['tactics']['lineup']:
                pid = item['player']['id']; ensure(pid, item['player']['name'], team(e), e['team']['name'])
                active[pid] = (0, item['position']['id'])
        if typ(e) == 'Tactical Shift':
            for item in e.get('tactics', {}).get('lineup', []):
                pid = item['player']['id']
                if pid in active:
                    close(pid, now); active[pid] = (now, item['position']['id'])
        pid = e.get('player', {}).get('id')
        pos = e.get('position', {}).get('id')
        if pid in active and pos is not None and pos != active[pid][1]:
            close(pid, now); active[pid] = (now, pos)
        if typ(e) == 'Substitution':
            outgoing_pos = active.get(pid, (0, pos))[1]
            close(pid, now)
            replacement = e['substitution']['replacement']; rid = replacement['id']
            explicit_pos = next((n['position']['id'] for n in events[i+1:] if n.get('player', {}).get('id') == rid and n.get('position')), outgoing_pos)
            ensure(rid, replacement['name'], team(e), e['team']['name']); active[rid] = (now, explicit_pos)
        card = e.get('foul_committed', e.get('bad_behaviour', {})).get('card', {}).get('name')
        if card in {'Red Card', 'Second Yellow'}: close(pid, now)
    for pid in list(active): close(pid, elapsed)
    return profiles, elapsed

def two_opponent_actions(events, i, cfg):
    loss = events[i]; actions = []
    for e in events[i+1:]:
        if e['period'] != loss['period'] or clock(e)-clock(loss) > cfg.control_window: break
        if stoppage(e): break
        if not is_ball_action(e, cfg): continue
        if team(e) == team(loss) or not controls_ball(e, cfg, second=bool(actions)): break
        if typ(e) == 'Carry' and clock(e)+e.get('duration',0)-clock(loss) > cfg.control_window: break
        actions.append(e)
        if len(actions) == 2: return actions
    return []

def match_calculations(raw, match, cfg):
    events = [e for e in raw if e['period'] <= 4]
    ids = {e['id']: e for e in events}
    profiles, duration = playing_time(events)
    counters = defaultdict(Counter)
    traces = {'pre': [], 'support': [], 'loss': []}
    quality = Counter()
    pre = calculate(raw, pre_window=cfg.pre_window)['pre_key_sequences']
    for chain in pre:
        owner = chain['pre_pass']['player']['id']; counters[owner]['pre_key'] += 1
        traces['pre'].append({'owner': owner, 'events': [summary(ids[chain[k]['id']], match) for k in ('pre_pass', 'key_pass', 'shot')]})
    groups = defaultdict(list)
    for e in events: groups[(e['period'], e['possession'])].append(e)
    used_controls = set()
    for i, e in enumerate(events):
        pid = e.get('player', {}).get('id')
        if pid is None: continue
        c = counters[pid]; p = e.get('pass', {})
        c.update(defensive_counts(e))
        if typ(e) == 'Pass':
            c['passes'] += 1; c['completed'] += complete(e)
            c['pressured_passes'] += bool(e.get('under_pressure'))
            c['pressured_completed'] += bool(e.get('under_pressure') and complete(e))
            if complete(e):
                if not p.get('type'): c['op_passes'] += 1
                if e.get('location') and p.get('end_location'):
                    c['deep_progressions'] += e['location'][0] < 80 <= p['end_location'][0]
                    if not p.get('type'): c['box_passes'] += not in_box(e['location']) and in_box(p['end_location'])
                    if e.get('under_pressure') and p.get('recipient'):
                        length = pass_length_metres(p)
                        if length is None: quality['missing_pressured_pass_length'] += 1
                        if length is not None and length <= 10:
                            rid = p['recipient']['id']; counters[rid]['short_receipts'] += 1
                            dx = p['end_location'][0] - e['location'][0]
                            selected = cfg.progress_min_x is None or dx >= cfg.progress_min_x
                            if selected: counters[rid]['support'] += 1
                            traces['support'].append({'owner':rid, 'events':[summary(e, match)], 'length_m':length, 'dx':dx, 'selected':selected, 'recipient':p['recipient']['name']})
                if not p.get('type') and p.get('assisted_shot_id') in ids: c['key_passes'] += 1
        if typ(e) == 'Carry' and e.get('location') and e.get('carry', {}).get('end_location'):
            c['deep_progressions'] += e['location'][0] < 80 <= e['carry']['end_location'][0]
        if typ(e) == 'Dribble' and e.get('dribble', {}).get('outcome', {}).get('name') == 'Complete': c['dribbles'] += 1
        if typ(e) == 'Shot': c['shots'] += 1
        if not loss_candidate(e) or e.get('out') or team(e) != e.get('possession_team', {}).get('id') or not e.get('location'): continue
        endpoint = p.get('end_location', e['location'])
        if endpoint[0] >= 80 or (cfg.both_loss_locations and e['location'][0] >= 80): continue
        history = [n for n in groups[(e['period'], e['possession'])] if n['index'] < e['index']]
        # Conservative history reset on opponent ball-control evidence, not possession ID alone.
        reset = max((n['index'] for n in history if team(n) != team(e) and is_ball_action(n, cfg) and controls_ball(n, cfg)), default=-1)
        prior = [n for n in history if n['index'] > reset and team(n) == team(e)]
        if not prior: continue
        age = clock(e)-clock(prior[0]); passes = sum(complete(n) for n in prior)
        visited = any(n.get('location', [0])[0] >= 80 or n.get('pass', {}).get('end_location', [0])[0] >= 80 or n.get('carry', {}).get('end_location', [0])[0] >= 80 for n in prior)
        if age < cfg.settle_seconds or passes < cfg.settle_passes or visited or e.get('play_pattern', {}).get('name') == 'From Counter': continue
        control = two_opponent_actions(events, i, cfg)
        if not control or control[0]['id'] in used_controls: continue
        used_controls.add(control[0]['id']); c['eligible_losses'] += 1
        shots = []; own_actions = 0
        for n in events[i+1:]:
            if n['period'] != e['period'] or clock(n)-clock(e) > cfg.shot_window or stoppage(n): break
            if n['index'] < control[1]['index']: continue
            if is_ball_action(n, cfg):
                if team(n) == team(e) and controls_ball(n, cfg, second=own_actions > 0): own_actions += 1
                else: own_actions = 0
                if own_actions >= 2: break
            if typ(n) == 'Shot' and team(n) != team(e):
                if in_box(n.get('location')): shots.append(n)
                if n.get('shot', {}).get('outcome', {}).get('name') == 'Goal': break
        if shots: c['dangerous_losses'] += 1
        sequence_events=list({n['id']:n for n in [e,*control,*shots]}.values())
        traces['loss'].append({'owner':pid, 'events':[summary(n, match) for n in sequence_events], 'control_event_ids':[n['id'] for n in control], 'shot_event_ids':[n['id'] for n in shots], 'dangerous':bool(shots), 'prior_passes':passes, 'phase_seconds':age, 'loss_endpoint':endpoint})
    return profiles, counters, traces, {'duration_seconds':duration, 'events_excluding_shootout':len(events), 'shootout_events_excluded':len(raw)-len(events), **quality}

def aggregate(cfg=Settings(), match_ids=None):
    matches = [m for m in read_matches() if match_ids is None or m['match_id'] in match_ids]
    rows, counts, all_traces, quality = {}, defaultdict(Counter), {'pre':[], 'support':[], 'loss':[]}, []
    for m in matches:
        path = DATA/f"raw/events/{m['match_id']}.json"
        raw = json.loads(gzip.decompress(path.with_suffix('.json.gz').read_bytes()).decode('utf-8'))
        profiles, cs, traces, q = match_calculations(raw, m, cfg)
        quality.append({'match_id':m['match_id'], **q})
        for pid, p in profiles.items():
            if pid not in rows: rows[pid] = {**p, 'seconds':0, 'role_seconds':Counter(), 'appearances':0}
            rows[pid]['seconds'] += p['seconds']; rows[pid]['role_seconds'].update(p['role_seconds']); rows[pid]['appearances'] += p['seconds'] > 0
        for pid, c in cs.items(): counts[pid].update(c)
        for key in all_traces: all_traces[key].extend(traces[key])
    result = []
    for pid, row in rows.items():
        c = counts[pid]; minutes = row['seconds']/60
        if minutes <= 0: continue
        row['minutes'] = minutes; row['role'] = max(row['role_seconds'], key=row['role_seconds'].get, default='other')
        row['counts'] = dict(c)
        for key in ('op_passes','deep_progressions','dribbles','key_passes','box_passes','shots','pre_key','support','tackles','pressures','opp_half_pressures','counterpressures','interceptions','recoveries','aerial_wins','dribbled_past'):
            row[f'{key}_p90'] = c[key]*90/minutes
        row['passing_pct'] = 100*c['completed']/c['passes'] if c['passes'] else None
        row['pressured_pct'] = 100*c['pressured_completed']/c['pressured_passes'] if c['pressured_passes'] else None
        row['dangerous_losses_total'] = c['dangerous_losses']
        row['aerial_win_pct'] = 100*c['aerial_wins']/(c['aerial_wins']+c['aerial_losses']) if c['aerial_wins']+c['aerial_losses'] else None
        result.append(row)
    return {'players':result, 'traces':all_traces, 'quality':quality, 'settings':asdict(cfg), 'match_count':len(matches), 'version':'demo-v4-count-and-defense-2026-10-23'}

def percentile(value, population):
    values = [float(x) for x in population if x is not None and math.isfinite(x)]
    if value is None or len(values) < 3: return None
    return 100*(sum(x < value for x in values)+0.5*sum(x == value for x in values))/len(values)

def cohort_rows(data, roles=('6','8','10'), min_minutes=120):
    return [p for p in data['players'] if p['role'] in roles and p['minutes'] >= min_minutes]

def scores(player, population, min_losses=5):
    output = {}
    for key, *_ in BASE_METRICS+CUSTOM_METRICS+DEFENSIVE_METRICS:
        valid = population
        value = player[key]
        direction = -1 if key in LOWER_IS_BETTER else 1
        output[key] = percentile(direction*value if value is not None else None, [direction*p[key] if p[key] is not None else None for p in valid])
    return output

def source_fingerprint():
    manifest = (DATA/'manifest.json').read_bytes()
    return hashlib.sha256(manifest+Path(__file__).read_bytes()+(ROOT/'scripts/calculate_candidate_pilot.py').read_bytes()).hexdigest()
