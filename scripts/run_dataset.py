import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from run_v4 import worker
from media_v3 import atomic_json
import argparse,json,time,multiprocessing as mp
from datetime import datetime,timezone
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--devices',type=int,default=1);ap.add_argument('--run',default='batch');ap.add_argument('--manifest',default='manifest.jsonl');args=ap.parse_args()
 root=Path(args.root).resolve();
 if args.devices<1:ap.error('devices must be positive')
 rows=[json.loads(l) for l in (root/'data-v3'/args.manifest).read_text().splitlines()]
 assert len(rows)>0 and len({r['clip_id'] for r in rows})==len(rows)
 assert all((root/'ocr/records'/(r['clip_id']+'.json')).exists() and (root/'rules/records'/(r['clip_id']+'.json')).exists() for r in rows)
 base=root/'outputs'/args.run;base.mkdir(parents=True,exist_ok=True)
 from media_v3 import digest
 repo=Path(__file__).resolve().parents[1]
 assert all((root/'src'/f.name).is_file() and digest(root/'src'/f.name)==digest(f) for f in (repo/'src').glob('*.py')),'code changed; use a new run root'
 assert all((root/'configs'/f.name).is_file() and digest(root/'configs'/f.name)==digest(f) for f in (repo/'configs').glob('*') if f.is_file()),'config changed; use a new run root'
 from models import qwen_receipt
 saved=json.loads((root/'model-receipt.json').read_text())
 assert qwen_receipt(root/'models/Qwen3-VL-8B-Instruct')['identity']==saved['identity'],'model changed; configure a new run'
 ctx=mp.get_context('spawn');out=ctx.Queue();ins=[ctx.Queue() for _ in range(args.devices)]
 ws=[ctx.Process(target=worker,args=(str(root),f'cuda:{i}',ins[i],out)) for i in range(args.devices)]
 events=[];t=time.monotonic();started_at=datetime.now(timezone.utc).isoformat()
 def receive(n):
  result=[]
  for _ in range(n):
   e=out.get(timeout=900);events.append(e);print('EVENT',json.dumps(e),flush=True)
   if 'fatal' in e:raise RuntimeError(e['traceback'])
   result.append(e)
  return result
 def dispatch(items,phase,dest):
  for i,row in enumerate(items):ins[i%args.devices].put((phase+'-'+row['clip_id'],[row],str(dest)))
  return receive(len(items))
 try:
  for p in ws:p.start()
  receive(args.devices)
  selected=[rows[i%len(rows)] for i in range(args.devices)]
  # One preflight per accelerator, including small batches.
  for i,row in enumerate(selected):ins[i].put(('preflight-'+str(i),[row],str(base/'preflight'/str(i))))
  pre=receive(args.devices)
  # Canary checks inference availability in every batch. Schema failures remain data,
  # never repaired or treated as an accepted result.
  checks=[]
  for i,row in enumerate(selected):
   rec=json.loads((base/'preflight'/str(i)/(row['clip_id']+'.json')).read_text())
   checks.append({'clip_id':row['clip_id'],'batch':row['batch_id'],'valid_passes':sum(bool(p.get('result')) for p in rec['passes']),'origin_gate_status':(rec.get('region_origin_gate') or {}).get('status'),'route':rec['overlay_route'],'reason':rec['routing_reason']})
  atomic_json(base/'preflight.json',{'events':pre,'checks':checks,'policy':'one fully schema-valid canary per visible device; fatal inference errors abort'})
  assert all(c['valid_passes']==2 for c in checks),checks
  assert all(c['origin_gate_status'] in ['success','no_text_candidates'] for c in checks),checks
  started=time.monotonic();production=dispatch(rows,'production',base/'records')
  failed=[r for r in rows if json.loads((base/'records'/(r['clip_id']+'.json')).read_text())['routing_reason']=='technical_failure']
  # Exactly one built-in record retry; maximum record_attempt=2 is enforced by v4.
  retry_start=time.monotonic();retry=dispatch(failed,'bounded-retry',base/'records') if failed else []
  atomic_json(base/'retry-execution.json',{'selected':[r['clip_id'] for r in failed],'events':retry,'wall_s':time.monotonic()-retry_start,'remaining_technical_failures':sum(e['technical_failures'] for e in retry),'policy':'v4 built-in record_attempt<=2; prompt and schema unchanged'})
  atomic_json(base/'execution.json',{'started_at':started_at,'completed_at':datetime.now(timezone.utc).isoformat(),'production_wall_s':retry_start-started,'retry_wall_s':time.monotonic()-retry_start,'worker_total_wall_s':time.monotonic()-t,'devices':args.devices,'production':production,'events':events,'final_technical_failures':sum(json.loads((base/'records'/(r['clip_id']+'.json')).read_text())['routing_reason']=='technical_failure' for r in rows),'completion_policy':'all requested records persisted; unresolved technical failures explicitly routed to review'})
 finally:
  for queue in ins:queue.put(None)
  for p in ws:
   p.join(timeout=10)
   if p.is_alive():p.terminate();p.join()
if __name__=='__main__':main()
