from pathlib import Path
import sys,json,time,concurrent.futures,multiprocessing as mp,copy,importlib.metadata
from PIL import Image
REPO=Path(__file__).resolve().parents[1];ROOT=REPO
sys.path.insert(0,str(REPO/'src'))
from media_v3 import digest,atomic_json,identity
from ocr_multiscale import make_engine,augment,ROIS
from rules import analyze
ENGINE=None
def init(root):
 global ENGINE,ROOT
 ROOT=Path(root)
 import cv2
 cv2.setNumThreads(1);ENGINE=make_engine(ROOT/'ocr/models/ch_PP-OCRv5_det_mobile.onnx')
def one(row):
 assert digest(ROOT/'data-v3'/row['path'])==row['sha256']
 assert digest(ROOT/'data-v3'/row['frames_manifest'])==row['frames_manifest_sha256']
 t=time.monotonic();out=ROOT/'ocr/records'/f"{row['clip_id']}.json";cfg=json.loads((ROOT/'ocr/config.json').read_text())
 if out.exists():
  old=json.loads(out.read_text());assert old['config_identity']==cfg['identity'] and old['clip_sha256']==row['sha256']
  if old['status']=='success':
   atomic_json(ROOT/'rules/records'/f"{row['clip_id']}.json",analyze(old,row['duration_s'],json.loads((ROOT/'rules/config.json').read_text())))
   return {'clip_id':row['clip_id'],'cached':True}
 fm=ROOT/'data-v3'/row['frames_manifest'];fs=json.loads(fm.read_text())['frames']
 result={'clip_id':row['clip_id'],'clip_sha256':row['sha256'],'frames_manifest_sha256':digest(fm),'config_identity':cfg['identity'],'status':'success','frames':{}}
 for f in fs:
  p=fm.parent/f['path'];assert digest(p)==f['sha256'];im=Image.open(p).convert('RGB')
  import numpy as np
  det=ENGINE(np.asarray(im)[:,:,::-1].copy(),use_det=True,use_cls=False,use_rec=False);boxes=[];w,h=im.size
  if det.boxes is not None:
   for i,(quad,score) in enumerate(zip(det.boxes,det.scores)):
    poly=[[float(x)/w,float(y)/h] for x,y in quad];b=[min(x for x,y in poly),min(y for x,y in poly),max(x for x,y in poly),max(y for x,y in poly)]
    boxes.append({'id':i,'bbox':b,'polygon':poly,'score':float(score)})
  st=time.monotonic();boxes=augment(im,boxes,ENGINE)
  result['frames'][f['path']]={'sha256':f['sha256'],'timestamp_s':f['timestamp_s'],'width':im.width,'height':im.height,'boxes':boxes,'elapsed_s':time.monotonic()-st}
 result['elapsed_s']=time.monotonic()-t;atomic_json(out,result)
 rule=analyze(result,row['duration_s'],json.loads((ROOT/'rules/config.json').read_text()))
 atomic_json(ROOT/'rules/records'/f"{row['clip_id']}.json",rule)
 return {'clip_id':row['clip_id'],'frames':len(fs),'boxes':sum(len(f['boxes']) for f in result['frames'].values()),'rule_labels':rule['labels'],'elapsed_s':result['elapsed_s']}
def main():
 global ROOT
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--manifest',default='manifest.jsonl');ap.add_argument('--workers',type=int,default=6);a=ap.parse_args();ROOT=Path(a.root).resolve()
 if a.workers<1:ap.error('workers must be positive')
 (ROOT/'ocr/records').mkdir(parents=True,exist_ok=True);(ROOT/'rules/records').mkdir(parents=True,exist_ok=True)
 cfg={'version':'ocr-region-r1','engine':'RapidOCR 3.10.0 PP-OCRv5 mobile detection','model_sha256':digest(ROOT/'ocr/models/ch_PP-OCRv5_det_mobile.onnx'),'full_frame_policy':'recompute same model max1536 for all samples','region_crop_policy':{'rois':ROIS,'upscale':2,'limit_type':'max','limit_side_len':1536,'box_thresh':.5},'nms':'intersection over smaller >= .8 AND area ratio .45..2.2','rule_config_sha256':digest(ROOT/'rules/config.json'),'candidate_policy':'up to16 per frame, region quota + full-frame fallback, geometry not semantic truth','recognition':False}
 cfg['identity']=identity(cfg)
 p=ROOT/'ocr/config.json'
 if p.exists():assert json.loads(p.read_text())==cfg
 else:atomic_json(p,cfg)
 rows=list(map(json.loads,(ROOT/'data-v3'/a.manifest).read_text().splitlines()))
 t=time.monotonic();results=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers,initializer=init,initargs=(str(ROOT),),mp_context=mp.get_context('spawn')) as ex:
  for result in ex.map(one,rows):results.append(result);print('OCR',json.dumps(result),flush=True)
 atomic_json(ROOT/'ocr'/f'execution-{a.manifest}.json',{'wall_s':time.monotonic()-t,'workers':a.workers,'rows':results})
if __name__=='__main__':main()
