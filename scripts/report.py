"""Export a self-contained cloud dashboard from exact per-clip predictions."""
import argparse,json,csv,shutil,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from media_v3 import atomic_json,digest,identity
REPO=Path(__file__).resolve().parents[1]
LABELS={'accept':'未遮挡操作','not_applicable':'不适用','review':'需复核','reject':'遮挡候选'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True)
    p.add_argument('--run',default='batch');p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.root).resolve();out=Path(a.output).resolve()
    if out.exists():raise ValueError('delivery exists; choose a new output for rollback')
    rows=[json.loads(l) for l in (root/'data-v3/manifest.jsonl').read_text().splitlines() if l.strip()]
    records=root/'outputs'/a.run/'records';data=root/'data-v3'
    # Validate completeness before creating a delivery.
    loaded=[]
    for row in rows:
        rec=json.loads((records/(row['clip_id']+'.json')).read_text())
        if rec['clip']!=row:raise ValueError('record does not match input '+row['clip_id'])
        loaded.append((row,rec))
    out.mkdir(parents=True);items=[]
    def asset(source,relative):
        dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest);return str(relative)
    for row,rec in loaded:
        cid=row['clip_id'];fm=data/row['frames_manifest'];frames=json.loads(fm.read_text())['frames']
        if digest(data/row['path'])!=row['sha256'] or digest(fm)!=row['frames_manifest_sha256']:raise ValueError('input hash changed')
        item={k:rec[k] for k in ['overlay_route','routing_reason','overlay_present','overlay_types','action_present','overlay_impact']}
        item.update(clip_id=cid,source_id=row['source_id'],split_group=row.get('split_group',row['source_id']),
                    source_url=row.get('source_url'),start_s=row.get('start_s',row.get('source_start_s',0)),end_s=row.get('end_s',row.get('source_end_s',row['duration_s'])),duration_s=row['duration_s'],
                    video=asset(data/row['path'],Path('videos')/(cid+'.mp4')),
                    thumbnail=asset(fm.parent/frames[len(frames)//2]['path'],Path('thumbnails')/(cid+'.jpg')),
                    record=asset(records/(cid+'.json'),Path('records')/(cid+'.json')),
                    evidence=[],origins=[],passes=[],human_label=None,label_origin='model_prediction')
        for pi,trial in enumerate(rec['passes']):
            item['passes'].append({'fps':trial['requested_fps'],'result':trial.get('result'),'error':trial.get('error')})
            for ei,ev in enumerate((trial.get('result') or {}).get('evidence',[])):
                f=trial['frames'][ev['frame_id']];src=fm.parent/f['path']
                if digest(src)!=f['sha256']:raise ValueError('evidence hash changed')
                item['evidence'].append(dict(ev,timestamp_s=f['timestamp_s'],fps=trial['requested_fps'],
                    image=asset(src,Path('evidence')/f'{cid}-{pi}-{ei}.jpg')))
        gate=rec.get('region_origin_gate') or {}
        item['origin_status']=gate.get('status')
        for candidate in gate.get('candidates',[]):
            crop=records/'origin-crops'/cid/(str(candidate['id'])+'.jpg')
            c=dict(candidate)
            if crop.exists():c['image']=asset(crop,Path('origins')/cid/crop.name)
            item['origins'].append(c)
        rule=json.loads((root/'rules/records'/(cid+'.json')).read_text());item['rule_labels']=rule['labels']
        items.append(item)
    counts={key:0 for key in LABELS};counts.update(Counter(x['overlay_route'] for x in items))
    dataset_id=identity({'manifest':digest(data/'manifest.jsonl'),'records':{x['clip_id']:digest(out/x['record']) for x in items}})
    summary={'dataset_id':dataset_id,'samples':len(items),'sources':len({x['source_id'] for x in items}),
             'counts':counts,'issues':dict(Counter(x['routing_reason'] for x in items)),
             'mode':'shadow_only','human_ground_truth':False}
    atomic_json(out/'dataset.json',{'summary':summary,'records':items});atomic_json(out/'summary.json',summary)
    keys=['clip_id','source_id','split_group','start_s','end_s','overlay_route','overlay_present','overlay_types','action_present','overlay_impact','routing_reason','video','record']
    with (out/'pipeline_data.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
        for item in items:writer.writerow({k:json.dumps(item[k],ensure_ascii=False) if isinstance(item[k],list) else item[k] for k in keys})
    shutil.copy2(REPO/'web/index.html',out/'index.html')
    execution=root/'outputs'/a.run/'execution.json'
    atomic_json(out/'resources.json',{'execution':json.loads(execution.read_text()) if execution.exists() else None,
                 'stages':{f.stem:json.loads(f.read_text()) for f in (root/'metrics').glob('*.json')}})
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
