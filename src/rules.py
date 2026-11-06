"""Geometry/time-only candidate rules. Never assigns semantic overlay types or deletion routes."""
import math, statistics as st
def area(b):return max(0,b[2]-b[0])*max(0,b[3]-b[1])
def intersection(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
def iou(a,b):
 v=intersection(a,b);return v/max(1e-12,area(a)+area(b)-v)
def center(b):return ((b[0]+b[2])/2,(b[1]+b[3])/2)
def zones(b,c):return [k for k,v in c['regions'].items() if intersection(b,v)/max(area(b),1e-12)>=c['box_fraction_in_roi']]
def angle(poly,width,height):
 if not poly or len(poly)<2:return 90
 dx=(poly[1][0]-poly[0][0])*width;dy=(poly[1][1]-poly[0][1])*height
 a=abs(math.degrees(math.atan2(dy,dx)))%180
 return min(a,180-a)
def analyze(ocr,duration,c):
 frames=[];seen=set();invalid=0;raw_boxes=0
 for name,f in sorted(ocr['frames'].items(),key=lambda x:(x[1]['timestamp_s'],x[0])):
  t=float(f['timestamp_s'])
  if t in seen:continue
  seen.add(t);frames.append((name,f))
 tracks=[];hits=0;outside=0;low=0;per_region={k:0 for k in c['regions']}
 for name,f in frames:
  t=float(f['timestamp_s']);items=[]
  for ob in f['boxes']:
   raw_boxes+=1;b=ob['bbox']
   if len(b)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in b) or b[0]>=b[2] or b[1]>=b[3]:
    invalid+=1;continue
   if ob['score']<c['min_score']:low+=1;continue
   z=zones(b,c)
   if not z:outside+=1;continue
   hits+=1
   for k in z:per_region[k]+=1
   items.append({'frame':name,'timestamp_s':t,'bbox':b,'ocr_id':ob['id'],'score':ob['score'],'zones':z,'angle_deg':angle(ob.get('polygon'),f['width'],f['height']),'pixel_aspect':(b[2]-b[0])*f['width']/max(1e-9,(b[3]-b[1])*f['height'])})
  used=set()
  for item in sorted(items,key=lambda x:x['score'],reverse=True):
   b=item['bbox'];best=None;bestscore=-1
   for idx,tr in enumerate(tracks):
    if idx in used:continue
    prev=tr[-1];gap=t-prev['timestamp_s']
    if not 0<gap<=c['tracking']['max_gap_s']:continue
    old=prev['bbox'];wr=(b[2]-b[0])/(old[2]-old[0]);hr=(b[3]-b[1])/(old[3]-old[1])
    d=math.dist(center(b),center(old));ov=iou(b,old)
    if not c['tracking']['min_width_ratio']<=wr<=c['tracking']['max_width_ratio'] or not .5<=hr<=2:continue
    if ov<c['tracking']['min_iou'] and d>c['tracking']['max_center_distance']:continue
    score=ov-d
    if score>bestscore:best=idx;bestscore=score
   if best is None:tracks.append([item]);used.add(len(tracks)-1)
   else:tracks[best].append(item);used.add(best)
 out=[]
 for i,tr in enumerate(tracks):
  n=len(tr);coverage=n/max(1,len(frames));span=tr[-1]['timestamp_s']-tr[0]['timestamp_s']
  centers=[center(x['bbox']) for x in tr];sx=st.pstdev(x[0] for x in centers);sy=st.pstdev(x[1] for x in centers)
  bz=c['bottom_text'];az=c['anchor_text']
  bottom=sum('bottom' in x['zones'] and x['bbox'][2]-x['bbox'][0]>=bz['min_width'] and x['bbox'][3]-x['bbox'][1]<=bz['max_height'] and x['pixel_aspect']>=bz['min_pixel_aspect'] and x['angle_deg']<=bz['max_angle_deg'] for x in tr)/n
  anchor=sum(any(z!='bottom' for z in x['zones']) and x['bbox'][2]-x['bbox'][0]<=az['max_width'] and x['bbox'][3]-x['bbox'][1]<=az['max_height'] for x in tr)/n
  labels=[]
  if bottom>=.8 and n>=bz['min_frames'] and span>=bz['min_span_s'] and coverage>=bz['min_clip_frame_fraction']:labels.append('bottom_horizontal_text')
  if anchor>=.8 and coverage>=az['min_clip_frame_fraction'] and span>=az['min_span_s'] and max(sx,sy)<=az['max_center_std']:labels.append('stable_corner_side_text')
  representative=min(tr,key=lambda x:abs(x['timestamp_s']-(tr[0]['timestamp_s']+tr[-1]['timestamp_s'])/2))
  out.append({'track_id':i,'labels':labels,'frame_fraction':round(coverage,5),'frames':n,'span_s':round(span,5),'center_std':[round(sx,5),round(sy,5)],'representative':representative,'observations':tr})
 return {'clip_id':ocr['clip_id'],'text_region_hits':hits,'raw_ocr_boxes':raw_boxes,'low_score_boxes':low,'outside_roi_boxes':outside,'invalid_boxes':invalid,'unique_frames':len(frames),'per_region_box_hits':per_region,'tracks':out,'labels':sorted(set(v for tr in out for v in tr['labels'])),'semantic_overlay_present':None,'routing_action':'keep_original_v4','limitations':['OCR text candidates only; graphic logos without text are not evaluated','Physical text/printed logos/whiteboards can pass these rules','No candidate is not evidence of no overlay; retain full-frame semantic review','No action-region localization: no occlusion conclusion']}
