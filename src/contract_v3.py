"""Evidence-grounded decisions. Valid JSON is not evidence of factual correctness."""
import json
import math

TYPES={'subtitle','logo','text_watermark','sticker','effect','mosaic','other'}
REASONS={'none','no_action','task_mismatch','sampling_insufficient','cause_uncertain',
         'natural_occlusion','blur','scene_transition','evidence_uncertain'}
FIELDS={'overlay_present','overlay_types','action_present','task_relevance','action_intervals',
        'key_action_visibility','temporal_adequacy','decision','observed_action',
        'other_limitations','review_reason','evidence'}
EV_FIELDS={'frame_id','timestamp_s','overlay_type','critical_region','overlay_region',
           'blocked_phase','reason'}


def numeric(v):
    return type(v) in (int,float) and math.isfinite(v)


def box(v,nullable=False):
    if v is None and nullable:return
    if not isinstance(v,list) or len(v)!=4 or not all(numeric(x) and 0<=x<=1 for x in v):
        raise ValueError('box requires normalized [x1,y1,x2,y2]')
    if v[0]>=v[2] or v[1]>=v[3]:raise ValueError('empty or reversed box')


def overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def validate(raw,duration,frames):
    v=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(v,dict) or set(v)!=FIELDS:raise ValueError('exact v3 fields required')
    for k in ('overlay_present','action_present'):
        if v[k] is not None and type(v[k]) is not bool:raise ValueError(k+' must be bool/null')
    if not isinstance(v['overlay_types'],list) or any(t not in TYPES for t in v['overlay_types']):raise ValueError('overlay types')
    if v['overlay_present'] is False and v['overlay_types']:raise ValueError('absent overlay has types')
    if v['task_relevance'] not in {'relevant','irrelevant','uncertain'}:raise ValueError('task relevance')
    if v['key_action_visibility'] not in {'clear','blocked','uncertain','not_applicable'}:raise ValueError('visibility')
    if v['temporal_adequacy'] not in {'adequate','insufficient','uncertain'}:raise ValueError('coverage')
    if v['decision'] not in {'accept','reject','review'}:raise ValueError('decision')
    if v['review_reason'] not in REASONS:raise ValueError('review reason')
    if not isinstance(v['observed_action'],str):raise ValueError('observed action')
    if not isinstance(v['other_limitations'],list) or any(not isinstance(x,str) for x in v['other_limitations']):raise ValueError('limitations')
    intervals=v['action_intervals']
    if not isinstance(intervals,list):raise ValueError('action intervals')
    for interval in intervals:
        if not isinstance(interval,dict) or set(interval)!={'start_s','end_s'}:raise ValueError('interval fields')
        a,b=interval['start_s'],interval['end_s']
        if not numeric(a) or not numeric(b) or not 0<=a<b<=duration:raise ValueError('interval bounds')
    if v['action_present'] is False and intervals:raise ValueError('no action with intervals')
    if not isinstance(v['evidence'],list):raise ValueError('evidence list')
    for ev in v['evidence']:
        if not isinstance(ev,dict) or set(ev)!=EV_FIELDS:raise ValueError('evidence fields')
        fid=ev['frame_id']
        if type(fid) is not int or not 0<=fid<len(frames):raise ValueError('unseen frame id')
        if not numeric(ev['timestamp_s']) or abs(ev['timestamp_s']-frames[fid]['timestamp_s'])>0.06:raise ValueError(f'timestamp disagrees with sampled frame: frame_id={fid} requires timestamp_s={frames[fid]["timestamp_s"]}; reported={ev["timestamp_s"]}. Reinspect the provided frame mapping; do not invent a new timestamp')
        if ev['overlay_type'] not in TYPES|{'none','unknown'}:raise ValueError('evidence overlay type')
        box(ev['critical_region'],v['decision']=='review');box(ev['overlay_region'],True)
        if not isinstance(ev['blocked_phase'],str) or not isinstance(ev['reason'],str) or not ev['reason'].strip():raise ValueError('evidence text')
    if v['decision']=='review':
        if v['review_reason']=='none':raise ValueError('review needs reason')
    else:
        if v['review_reason']!='none' or v['action_present'] is not True or not intervals or not v['observed_action'].strip():raise ValueError('accept/reject requires action_present=true, nonempty observed_action/action_intervals, review_reason=none; if no action use decision=review, review_reason=no_action, evidence=[]')
        if v['task_relevance']!='relevant' or v['temporal_adequacy']!='adequate' or not v['evidence']:raise ValueError('decisive coverage prerequisites')
        if not any(any(a['start_s']<=e['timestamp_s']<=a['end_s'] for a in intervals) for e in v['evidence']):raise ValueError('evidence outside action intervals')
    if v['decision']=='accept' and v['key_action_visibility']!='clear':raise ValueError('accept requires clear')
    if v['decision']=='reject':
        if v['overlay_present'] is not True or not v['overlay_types'] or v['key_action_visibility']!='blocked':raise ValueError('reject overlay prerequisites')
        grounded=[e for e in v['evidence'] if e['overlay_type'] in v['overlay_types'] and e['overlay_region'] is not None
                  and overlap(e['critical_region'],e['overlay_region'])>0 and e['blocked_phase'].strip()
                  and any(a['start_s']<=e['timestamp_s']<=a['end_s'] for a in intervals)]
        if not grounded:raise ValueError('reject needs intersecting overlay/critical region at action time')
    return v


def validate_verifier(raw):
    v=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(v,dict) or set(v)!={'overlay_covers_critical_region','necessary_phase_unobservable','cause_is_overlay','reason'}:raise ValueError('verifier fields')
    for k in ('overlay_covers_critical_region','necessary_phase_unobservable','cause_is_overlay'):
        if v[k] is not None and type(v[k]) is not bool:raise ValueError('verifier bool/null')
    if not isinstance(v['reason'],str) or not v['reason'].strip():raise ValueError('verifier reason')
    return v


def aggregate(passes,verification=None):
    if not passes or any(p.get('error') or not p.get('result') for p in passes):return 'review','technical_failure'
    results=[p['result'] for p in passes];decisions={r['decision'] for r in results}
    if len(decisions)!=1:return 'review','sampling_disagreement'
    decision=next(iter(decisions))
    if decision=='review':
        reasons={r['review_reason'] for r in results}
        return 'review',next(iter(reasons)) if len(reasons)==1 else 'mixed_review_reasons'
    if len(results)<2:return 'review','verification_missing'
    if decision=='accept':return 'accept','sampled_overlay_check_passed'
    # Match space, time and overlay type, rather than only the decision enum.
    matched=any(a['overlay_type']==b['overlay_type'] and a['overlay_type'] in TYPES
                and a['overlay_region'] is not None and b['overlay_region'] is not None
                and overlap(a['critical_region'],b['critical_region'])>0
                and overlap(a['overlay_region'],b['overlay_region'])>0
                and overlap(a['critical_region'],a['overlay_region'])>0
                and overlap(b['critical_region'],b['overlay_region'])>0
                and abs(a['timestamp_s']-b['timestamp_s'])<=1.0
                for a in results[0]['evidence'] for b in results[1]['evidence'])
    if not matched:return 'review','evidence_disagreement'
    if not verification or verification.get('error'):return 'review','spatial_verification_failed'
    v=verification.get('result',{})
    if not all(v.get(k) is True for k in ('overlay_covers_critical_region','necessary_phase_unobservable','cause_is_overlay')):
        return 'review','spatial_verification_uncertain'
    return 'reject','overlay_blockage_candidate'
