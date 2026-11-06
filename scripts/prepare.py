"""Build non-overlapping fixed-duration clips and measured-PTS frame caches."""
import argparse,json,math,shutil,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from media_v3 import atomic_json,digest,identity,probe,clip_source,cache_frames
REPO=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',required=True,help='JSONL: source_id, path, task; optional source_url, split_group')
    p.add_argument('--root',required=True);p.add_argument('--limit',type=int,default=500)
    p.add_argument('--clip-seconds',type=float,default=5);p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.limit<1 or not 0<a.clip_seconds<=10:p.error('limit >= 1; clip-seconds in (0,10]')
    root=Path(a.root).resolve();sources=[json.loads(l) for l in Path(a.sources).read_text().splitlines() if l.strip()]
    ids=set();plan=[];content=set()
    for s in sources:
        sid=s['source_id']
        if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',sid) or sid in ids:raise ValueError('source_id must be unique safe text')
        ids.add(sid);src=Path(s['path']).expanduser().resolve()
        if not src.is_file():raise ValueError('missing source '+str(src))
        h=digest(src)
        if h in content:raise ValueError('duplicate source content')
        content.add(h)
        duration=float(probe(src)['format']['duration'])
        for i in range(math.floor((duration+1e-6)/a.clip_seconds)):
            if len(plan)>=a.limit:break
            plan.append({'source_id':sid,'source_path':str(src),'source_sha256':h,
                'start_s':i*a.clip_seconds,'end_s':(i+1)*a.clip_seconds,'task':s.get('task','human manipulation'),
                'source_url':s.get('source_url'),'split_group':s.get('split_group',sid)})
        if len(plan)>=a.limit:break
    if not plan:raise ValueError('no complete fixed-duration windows')
    print(json.dumps({'clips':len(plan),'sources':len({x['source_id'] for x in plan}),'selection':'input order, non-overlap; no scene detection','dry_run':a.dry_run}))
    if a.dry_run:return
    data=root/'data-v3';data.mkdir(parents=True,exist_ok=True)
    receipt=data/'plan.json'
    if receipt.exists() and json.loads(receipt.read_text())!=plan:raise ValueError('input changed; use a new root')
    atomic_json(receipt,plan)
    for folder in ['src','configs']:
        dest=root/folder
        if dest.exists():
            for f in (REPO/folder).glob('*'):
                if f.is_file() and (dest/f.name).exists() and digest(dest/f.name)!=digest(f):raise ValueError('code/config changed; use new root')
        dest.mkdir(exist_ok=True)
        for f in (REPO/folder).glob('*'):
            if f.is_file():shutil.copy2(f,dest/f.name)
    (root/'rules').mkdir(exist_ok=True)
    shutil.copy2(REPO/'configs/region_rules.json',root/'rules/config.json')
    rows=[]
    for item in plan:
        clip,cr=clip_source(item['source_path'],item['source_sha256'],item['start_s'],item['end_s'],data/'clips')
        fm,frames=cache_frames(clip,data/'frames',fps=8)
        row=dict(item,clip_id=item['source_id']+'-'+str(round(item['start_s']*1000)).zfill(9),
                 batch_id='input',path=str(clip.relative_to(data)),sha256=cr['sha256'],duration_s=cr['duration_s'],
                 frames_manifest=str(fm.relative_to(data)),frames_manifest_sha256=digest(fm))
        rows.append(row)
    tmp=data/'manifest.jsonl.tmp';tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows));tmp.replace(data/'manifest.jsonl')
    atomic_json(root/'input-identity.json',{'manifest_sha256':digest(data/'manifest.jsonl'),'plan_identity':identity(plan),'clips':len(rows)})
if __name__=='__main__':main()
