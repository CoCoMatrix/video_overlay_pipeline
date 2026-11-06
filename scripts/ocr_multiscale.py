from pathlib import Path
import sys,json,time,math,copy
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from media_v3 import digest,atomic_json,identity
from rapidocr import RapidOCR,OCRVersion,ModelType
ROIS={'bottom':[0,.65,1,1],'top':[0,0,1,.25],'left':[0,.2,.2,.8],'right':[.8,.2,1,.8]}
def make_engine(model):
 return RapidOCR(params={'Global.use_cls':False,'Global.use_rec':False,'Global.log_level':'error','Det.model_path':str(model),'Det.ocr_version':OCRVersion.PPOCRV5,'Det.model_type':ModelType.MOBILE,'Det.limit_type':'max','Det.limit_side_len':1536,'Det.box_thresh':.5,'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1})
def overlap(a,b):
 inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
 return inter/max(1e-9,min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1])))
def augment(im,base,engine):
 w,h=im.size;boxes=copy.deepcopy(base)
 for b in boxes:b['origin']=['full_frame']
 for name,roi in ROIS.items():
  x1,y1,x2,y2=[round(v*s) for v,s in zip(roi,[w,h,w,h])]
  cr=im.crop((x1,y1,x2,y2));cw,ch=cr.size;cr=cr.resize((cw*2,ch*2))
  out=engine(np.asarray(cr)[:,:,::-1].copy(),use_det=True,use_cls=False,use_rec=False)
  if out.boxes is None:continue
  for quad,score in zip(out.boxes,out.scores):
   poly=[[(float(x)/2+x1)/w,(float(y)/2+y1)/h] for x,y in quad]
   bb=[min(p[0] for p in poly),min(p[1] for p in poly),max(p[0] for p in poly),max(p[1] for p in poly)]
   bb=[max(0,min(1,v)) for v in bb]
   if bb[0]>=bb[2] or bb[1]>=bb[3]:continue
   matched=next((b for b in boxes if overlap(b['bbox'],bb)>=.8 and .45<=((b['bbox'][2]-b['bbox'][0])*(b['bbox'][3]-b['bbox'][1]))/max(1e-9,(bb[2]-bb[0])*(bb[3]-bb[1]))<=2.2),None)
   if matched:matched['origin'].append(name);matched['score']=max(matched['score'],float(score))
   else:boxes.append({'id':len(boxes),'bbox':[round(v,5) for v in bb],'polygon':[[round(x,5),round(y,5)] for x,y in poly],'score':float(score),'origin':[name]})
 for i,b in enumerate(boxes):b['id']=i
 return boxes