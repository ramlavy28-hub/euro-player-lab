"""Offline, auditable candidate sequence pilot. Provisional rules, not club KPIs."""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/candidate-pilot/v2-short-pass'
STOP = {'Half End', 'Foul Committed', 'Foul Won', 'Offside', 'Injury Stoppage', 'Referee Ball-Drop'}
MID = {9, 10, 11, 13, 14, 15, 18, 19, 20}
YARDS_TO_METRES = 0.9144

def pass_length_metres(pass_data):
    """Convert provider's yards to metres; never invent missing lengths."""
    yards = pass_data.get('length')
    if isinstance(yards, bool) or not isinstance(yards, (int, float)):
        return None
    if not math.isfinite(yards) or yards < 0:
        return None
    return yards * YARDS_TO_METRES

def clock(e):
    h, m, s = map(float, e['timestamp'].split(':'))
    return h * 3600 + m * 60 + s

def typ(e): return e['type']['name']
def team(e): return e.get('team', {}).get('id')
def complete(e): return typ(e) == 'Pass' and 'outcome' not in e.get('pass', {})
def same(a, b): return a['period'] == b['period'] and a['possession'] == b['possession'] and team(a) == team(b)
def brief(e):
    return {k: e.get(k) for k in ('id', 'index', 'period', 'timestamp', 'possession', 'player', 'team', 'location', 'position')} | {'type': typ(e)}

def controlled(e):
    t = typ(e)
    return (t in {'Pass', 'Carry', 'Shot'} or
            (t == 'Ball Receipt*' and not e.get('ball_receipt', {}).get('outcome')) or
            (t == 'Ball Recovery' and not e.get('ball_recovery', {}).get('recovery_failure')) or
            (t == 'Dribble' and e.get('dribble', {}).get('outcome', {}).get('name') == 'Complete'))

def loss_candidate(e):
    t = typ(e)
    return (t in {'Miscontrol', 'Dispossessed'} or
            (t == 'Dribble' and e.get('dribble', {}).get('outcome', {}).get('name') == 'Incomplete') or
            (t == 'Pass' and e.get('pass', {}).get('outcome', {}).get('name') == 'Incomplete'))

def calculate(events, pre_window=10, progression=10, settle_seconds=8, settle_passes=3, shot_window=15, max_pass_m=10):
    es = [e for e in events if e['period'] <= 4]
    ids = {e['id']: e for e in es}
    by_pos = defaultdict(list)
    for e in es: by_pos[(e['period'], e['possession'])].append(e)
    pre, receives, all_pressure, short_pressure, losses, loss_reviews = [], [], [], [], [], []
    diagnostics = Counter()
    for i, e in enumerate(es):
        p = e.get('pass', {})
        # Strict chain: completed delivery to key passer; only own receipt/carry
        # annotations may intervene. No implicit same-team event = a pass.
        if complete(e) and p.get('assisted_shot_id') in ids:
            shot = ids[p['assisted_shot_id']]
            if typ(shot) != 'Shot' or not same(e, shot):
                diagnostics['invalid_assisted_shot_link'] += 1
                continue
            diagnostics['eligible_key_passes'] += 1
            for a in reversed(es[:i]):
                if not same(a, e) or clock(e) - clock(a) > pre_window: break
                if typ(a) in {'Pressure', 'Duel', 'Interception', 'Block'}: break
                if typ(a) in {'Carry', 'Ball Receipt*'} and a.get('player', {}).get('id') == e.get('player', {}).get('id'): continue
                if complete(a) and a.get('pass', {}).get('recipient', {}).get('id') == e.get('player', {}).get('id') and not a.get('pass', {}).get('type') and not p.get('type'):
                    pre.append({'pre_pass': brief(a), 'key_pass': brief(e), 'shot': brief(shot), 'shot_xg': shot['shot']['statsbomb_xg']})
                break
        if complete(e) and e.get('under_pressure') and p.get('recipient') and e.get('location') and p.get('end_location'):
            # Includes all completion types; rule explicit, not official provider progression.
            dx = p['end_location'][0] - e['location'][0]
            distance_m = pass_length_metres(p)
            row = {'pass': brief(e), 'recipient': p['recipient'], 'end_location': p['end_location'], 'dx': round(dx, 3), 'pass_length_yards': p.get('length'), 'pass_length_m': distance_m}
            all_pressure.append(row)
            if distance_m is None:
                diagnostics['pressured_completed_pass_missing_or_invalid_length'] += 1
            within_length = distance_m is not None and (max_pass_m is None or distance_m <= max_pass_m)
            if within_length:
                short_pressure.append(row)
                if dx >= progression: receives.append(row)
        if not loss_candidate(e) or team(e) != e.get('possession_team', {}).get('id') or not e.get('location'): continue
        diagnostics['candidate_loss_events'] += 1
        # Origin AND delivery endpoint in own two thirds: deliberate conservative rule.
        end = p.get('end_location', e['location'])
        if e['location'][0] >= 80 or end[0] >= 80: continue
        diagnostics['candidate_losses_both_locations_below80'] += 1
        history = [a for a in by_pos[(e['period'], e['possession'])] if a['index'] < e['index']]
        reset = max((a['index'] for a in history if team(a) != team(e) and controlled(a)), default=-1)
        prior = [a for a in history if a['index'] > reset and team(a) == team(e)]
        if not prior: continue
        age = clock(e) - clock(prior[0])
        passes = sum(complete(a) for a in prior)
        visited_final = any(a.get('location', [0])[0] >= 80 or a.get('pass', {}).get('end_location', [0])[0] >= 80 or a.get('carry', {}).get('end_location', [0])[0] >= 80 for a in prior)
        pattern = e.get('play_pattern', {}).get('name')
        eligible = age >= settle_seconds and passes >= settle_passes and not visited_final and pattern != 'From Counter'
        if not eligible: continue
        diagnostics['phase_proxy_candidate_events'] += 1
        # Loss must lead to opponent controlled possession within five seconds,
        # without stoppage or intervening controlled team action. Dedup via first loss.
        control = None
        for nxt in es[i+1:]:
            if nxt['period'] != e['period'] or clock(nxt) - clock(e) > 5: break
            if typ(nxt) in STOP or nxt.get('out') or e.get('out'): break
            if controlled(nxt):
                if team(nxt) != team(e): control = nxt
                break
        review = {'loss': brief(e), 'end_location': end, 'phase_proxy': {'age_seconds': round(age, 3), 'prior_completed_passes': passes, 'previous_final_third_entry': visited_final, 'play_pattern': pattern}, 'opponent_control': brief(control) if control else None}
        loss_reviews.append(review)
        if control is None: continue
        if any(x['opponent_control']['id'] == control['id'] for x in losses): continue
        shots = []
        for nxt in es[i+1:]:
            dt = clock(nxt) - clock(e)
            if nxt['period'] != e['period'] or dt > shot_window: break
            if typ(nxt) in STOP or nxt.get('out'): break
            if controlled(nxt) and team(nxt) == team(e): break
            if nxt['index'] >= control['index'] and nxt['possession'] != control['possession']: break
            if typ(nxt) == 'Shot' and team(nxt) != team(e):
                shots.append(brief(nxt) | {'xg': nxt['shot']['statsbomb_xg'], 'elapsed_from_loss': round(dt, 3)})
        losses.append(review | {'shots': shots, 'shot_xg_sum': sum(s['xg'] for s in shots)})
    stats = defaultdict(lambda: {'pre_key_passes': 0, 'pressure_receptions': 0, 'short_pressure_receptions': 0, 'progressing_pressure_receptions': 0, 'eligible_build_up_losses': 0, 'losses_followed_by_shot': 0, 'following_shot_xg_sum': 0.0})
    names, teams, positions = {}, {}, defaultdict(Counter)
    for e in es:
        player = e.get('player')
        if player:
            pid = player['id']; names[pid] = player['name']; teams[pid] = e['team']['name']
            positions[pid][e.get('position', {}).get('id')] += 1
            stats[pid]
    for r in pre: stats[r['pre_pass']['player']['id']]['pre_key_passes'] += 1
    for r in all_pressure: stats[r['recipient']['id']]['pressure_receptions'] += 1
    for r in short_pressure: stats[r['recipient']['id']]['short_pressure_receptions'] += 1
    for r in receives: stats[r['recipient']['id']]['progressing_pressure_receptions'] += 1
    for r in losses:
        s = stats[r['loss']['player']['id']]
        s['eligible_build_up_losses'] += 1
        s['losses_followed_by_shot'] += bool(r['shots'])
        s['following_shot_xg_sum'] += r['shot_xg_sum']
    players = []
    for pid, s in stats.items():
        pos = positions[pid].most_common(1)[0][0] if positions[pid] else None
        players.append({'player_id': pid, 'player': names.get(pid, str(pid)), 'team': teams.get(pid), 'dominant_event_position_id': pos, 'midfield_display_filter': pos in MID, **s,
                        'progressing_share_of_short': s['progressing_pressure_receptions']/s['short_pressure_receptions'] if s['short_pressure_receptions'] else None,
                        'dangerous_loss_share': s['losses_followed_by_shot']/s['eligible_build_up_losses'] if s['eligible_build_up_losses'] else None})
    assert len({r['pre_pass']['id'] for r in pre}) == len(pre)
    assert all(r['dx'] >= progression for r in receives)
    assert all(max_pass_m is None or r['pass_length_m'] <= max_pass_m for r in receives)
    assert all(s['elapsed_from_loss'] <= shot_window for r in losses for s in r['shots'])
    return {'settings': {'pre_window': pre_window, 'progression_x_units': progression, 'max_pass_metres': max_pass_m, 'length_source': 'pass.length in provider yards * 0.9144; standardized event distance, not tracking-measured separation', 'settle_seconds': settle_seconds, 'settle_passes': settle_passes, 'shot_window': shot_window},
            'totals': {'pre_key_passes': len(pre), 'pressure_receptions': len(all_pressure), 'short_pressure_receptions': len(short_pressure), 'progressing_pressure_receptions': len(receives), 'eligible_build_up_losses': len(losses), 'losses_followed_by_shot': sum(bool(r['shots']) for r in losses), 'following_shot_xg_sum': sum(r['shot_xg_sum'] for r in losses)},
            'diagnostics': dict(diagnostics), 'players': players, 'pre_key_sequences': pre, 'progressing_receipts': receives, 'short_pressure_receipts': short_pressure, 'all_pressure_receipts': all_pressure, 'build_up_loss_sequences': losses, 'phase_proxy_reviews': loss_reviews}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for label, path in [('euro', ROOT/'research/womens-euro-sample/raw/events/4020846.json'), ('leverkusen', ROOT/'research/leverkusen-sample/raw/events/3895348.json')]:
        raw = path.read_bytes(); events = json.loads(raw)
        result = calculate(events)
        result['version'] = 'v2: user length cap <=10m; prior progression criterion retained'
        result['source'] = {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(raw).hexdigest(), 'excluded_period5': sum(e['period'] == 5 for e in events)}
        result['sensitivity'] = []
        for change in [{'progression': 0.000001}, {'progression': 5}, {'progression': 15}, {'max_pass_m': None}, {'pre_window': 5}, {'pre_window': 15}, {'shot_window': 10}, {'shot_window': 20}, {'settle_seconds': 5, 'settle_passes': 2}, {'settle_seconds': 12, 'settle_passes': 4}]:
            alt = calculate(events, **change)
            result['sensitivity'].append({'change': change, 'totals': alt['totals']})
        (OUT/f'{label}-sequences.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        with (OUT/f'{label}-players.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(result['players'][0])); writer.writeheader(); writer.writerows(result['players'])
        print(label, json.dumps(result['totals']), 'diagnostics', json.dumps(result['diagnostics']))
        for p in result['players']:
            if p['midfield_display_filter']: print(json.dumps(p, ensure_ascii=False))

if __name__ == '__main__': main()
