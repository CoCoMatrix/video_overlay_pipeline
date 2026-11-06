"""Separate visual overlay inventory from action applicability. Timestamps are mapped in code."""
import json,math
from contract_v3 import box,overlap,validate_verifier
TYPES={'subtitle','title_text','text_watermark','logo','sticker','effect','mosaic','other'}
FIELDS={'overlay_present','overlay_types','action_present','overlay_impact','observed_action','action_intervals','reason','evidence'}
EV={'frame_id','overlay_type','overlay_region','critical_region','blocked_phase','reason'}

def validate(raw,duration,frames,ocr):
 v=json.loads(raw) if isinstance(raw,str) else raw
 if not isinstance(v,dict) or set(v)!=FIELDS:raise ValueError('exact v4 fields required')
 for k in ['overlay_present','action_present']:
  if v[k] is not None and type(v[k]) is not bool:raise ValueError(k+' bool/null required')
 if not isinstance(v['overlay_types'],list) or any(x not in TYPES for x in v['overlay_types']):raise ValueError('overlay_types enum')
 if v['overlay_present'] is False and v['overlay_types']:raise ValueError('absent overlays require empty types')
 if v['overlay_present'] is True and not v['overlay_types']:raise ValueError('present overlays require types')
 impact=v['overlay_impact'];action=v['action_present']
 if impact not in {'none','blocks_key_action','uncertain','not_applicable'}:raise ValueError('overlay_impact enum')
 if action is False and impact!='not_applicable':raise ValueError('action_present=false requires overlay_impact=not_applicable; still assess overlay_present/types')
 if action is True and impact=='not_applicable':raise ValueError('action_present=true cannot be not_applicable')
 if action is None and impact!='uncertain':raise ValueError('unknown action requires uncertain impact')
 if v['overlay_present'] is False and action is True and impact!='none':raise ValueError('absent overlay with action implies impact none')
 for k in ['observed_action','reason']:
  if not isinstance(v[k],str):raise ValueError(k+' string required')
 if not v['reason'].strip():raise ValueError('reason required')
 spans=v['action_intervals']
 if not isinstance(spans,list):raise ValueError('action_intervals list')
 for a in spans:
  if not isinstance(a,dict) or set(a)!={'start_s','end_s'}:raise ValueError('action interval fields')
  if any(type(a[k]) not in (int,float) or not math.isfinite(a[k]) for k in a):raise ValueError('finite times required')
  if not 0<=a['start_s']<a['end_s']<=duration:raise ValueError('interval out of bounds')
 if action is False and spans:raise ValueError('no action requires empty action_intervals')
 if action is True and (not spans or not v['observed_action'].strip()):raise ValueError('visible action requires observed_action and intervals')
 if not isinstance(v['evidence'],list) or not 1<=len(v['evidence'])<=3:raise ValueError('provide 1 to 3 evidence frames, including absent-overlay or no-action examples')
 for e in v['evidence']:
  if not isinstance(e,dict) or set(e)!=EV:raise ValueError('evidence missing='+str(sorted(EV-set(e)))+' extra='+str(sorted(set(e)-EV))+'; output all six evidence fields, no OCR IDs')
  i=e['frame_id']
  if type(i) is not int or not 0<=i<len(frames):raise ValueError('unknown frame_id')
  if e['overlay_type'] not in TYPES|{'none','unknown'}:raise ValueError('evidence overlay_type')
  box(e['overlay_region'],True);box(e['critical_region'],True)
  if action is False and e['critical_region'] is not None:raise ValueError('no action: critical_region=null, do not invent interaction box')
  if e['overlay_type'] in TYPES:
   if e['overlay_region'] is None:raise ValueError('visible overlay needs a bounding box')
   if v['overlay_present'] is False:raise ValueError('absent overlay contradicts overlay evidence')
  if e['overlay_type']=='none' and e['overlay_region'] is not None:raise ValueError('no overlay requires overlay_region=null')
  if not all(isinstance(e[k],str) for k in ['blocked_phase','reason']) or not e['reason'].strip():raise ValueError('evidence text required')
 if v['overlay_present'] is True and not any(e['overlay_type'] in v['overlay_types'] for e in v['evidence']):raise ValueError('present overlay needs matching evidence')
 if impact=='blocks_key_action':
  if action is not True or v['overlay_present'] is not True:raise ValueError('blocking requires actual action and overlay')
  if not any(e['overlay_region'] is not None and e['critical_region'] is not None and overlap(e['overlay_region'],e['critical_region'])>0 and e['blocked_phase'].strip() and any(a['start_s']<=frames[e['frame_id']]['timestamp_s']<=a['end_s'] for a in spans) for e in v['evidence']):raise ValueError('blocking needs intersecting boxes and blocked phase at action time')
 return v

def aggregate(passes,verification=None):
 results=[p.get('result') for p in passes]
 if len(results)<2 or any(p.get('error') or not p.get('result') for p in passes):
  return {'overlay_present':None,'overlay_types':[],'action_present':None,'overlay_impact':'uncertain','overlay_route':'review','routing_reason':'technical_failure'}
 def common(key):
  values=[r[key] for r in results]
  return values[0] if all(v==values[0] for v in values) else None
 present=common('overlay_present');action=common('action_present')
 types=sorted(set(t for r in results for t in r['overlay_types']))
 impact=common('overlay_impact') or 'uncertain'
 out={'overlay_present':present,'overlay_types':types,'action_present':action,'overlay_impact':impact,'overlay_route':'review','routing_reason':'sampling_disagreement'}
 if action is False:out['overlay_impact']='not_applicable'
 if present is None:return out
 if any(set(r['overlay_types'])!=set(results[0]['overlay_types']) for r in results[1:]):
  out['routing_reason']='overlay_type_disagreement';return out
 if action is False:
  out.update(overlay_route='not_applicable',routing_reason='overlay_inventory_complete_no_action');return out
 if action is None:return out
 if impact=='none':
  out.update(overlay_route='accept',routing_reason='overlay_not_blocking_sampled_action');return out
 if impact!='blocks_key_action':
  out['routing_reason']='impact_uncertain';return out
 matched=any(a['overlay_type']==b['overlay_type'] and a['overlay_region'] is not None and b['overlay_region'] is not None and a['critical_region'] is not None and b['critical_region'] is not None and overlap(a['overlay_region'],b['overlay_region'])>0 and overlap(a['critical_region'],b['critical_region'])>0 and abs(passes[0]['frames'][a['frame_id']]['timestamp_s']-passes[1]['frames'][b['frame_id']]['timestamp_s'])<=1 for a in results[0]['evidence'] for b in results[1]['evidence'])
 if not matched:out['routing_reason']='blocking_evidence_disagreement';return out
 if not verification or verification.get('error'):out['routing_reason']='blocking_verification_missing_or_failed';return out
 if all(verification['result'].get(k) is True for k in ['overlay_covers_critical_region','necessary_phase_unobservable','cause_is_overlay']):
  out.update(overlay_route='reject',routing_reason='verified_overlay_blockage_candidate')
 else:out['routing_reason']='blocking_verification_uncertain'
 return out

def match_ocr(evidence,lookup):
 """Geometric correspondence only; never treated as semantic truth."""
 mapped=[]
 for i,e in enumerate(evidence):
  b=e['overlay_region']
  ids=[] if b is None else [j for j,c in lookup[e['frame_id']].items() if overlap(b,c['bbox'])>0]
  mapped.append({'evidence_index':i,'frame_id':e['frame_id'],'ocr_ids':ids,'method':'same_frame_box_intersection','semantic_confirmation':False})
 return mapped
