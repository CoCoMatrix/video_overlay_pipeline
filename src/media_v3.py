"""Content-addressed source clipping and frame caches with measured timestamps."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))


def ffmpeg_version():
    return subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]


def clip_source(source,source_sha,start,end,out):
    if not 0<=start<end:raise ValueError('invalid clip interval')
    if digest(source)!=source_sha:raise ValueError('source checksum mismatch')
    recipe={'source_sha256':source_sha,'start_s':start,'end_s':end,'codec':'libx264',
            'crf':20,'max_width':1280,'pixel_format':'yuv420p','ffmpeg':ffmpeg_version()}
    key=identity(recipe)[:20];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    path=out/(key+'.mp4');receipt=out/(key+'.json')
    if path.exists() and receipt.exists():
        saved=json.loads(receipt.read_text())
        if saved['recipe']==recipe and saved['sha256']==digest(path):return path,saved
        raise ValueError('clip cache corruption')
    tmp=path.with_suffix('.partial.mp4')
    subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-ss',str(start),'-i',str(source),
                    '-t',str(end-start),'-an','-vf',"scale='min(1280,iw)':-2",'-c:v','libx264',
                    '-preset','fast','-crf','20','-pix_fmt','yuv420p','-threads','2',
                    '-movflags','+faststart','-y',str(tmp)],check=True)
    actual=float(probe(tmp)['format']['duration']);tmp.replace(path)
    saved={'recipe':recipe,'sha256':digest(path),'duration_s':actual};atomic_json(receipt,saved)
    return path,saved


def cache_frames(clip,out,fps=8,width=960):
    recipe={'clip_sha256':digest(clip),'fps':fps,'max_width':width,'format':'jpeg_q2',
            'ffmpeg':ffmpeg_version(),'timestamp_source':'showinfo after select before resize'}
    key=identity(recipe)[:20];folder=Path(out)/key;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'frames.json'
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        if saved['recipe']!=recipe:raise ValueError('frame cache mismatch')
        if all((folder/f['path']).exists() and digest(folder/f['path'])==f['sha256'] for f in saved['frames']):return receipt,saved
        raise ValueError('frame cache corruption')
    vf=f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{1/fps-0.001})',showinfo,scale='min({width},iw)':-2"
    sync_flag='-fps_mode' if '-fps_mode' in subprocess.check_output(['ffmpeg','-hide_banner','-h','full'],text=True,stderr=subprocess.DEVNULL) else '-vsync'
    r=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-threads','1','-i',str(clip),'-an','-vf',vf,
                      sync_flag,'vfr','-q:v','2','-threads','1','-y',str(folder/'%05d.jpg')],capture_output=True,text=True,check=True)
    times=[float(t) for t in re.findall(r'pts_time:([0-9.]+)',r.stderr)]
    files=sorted(folder.glob('*.jpg'))
    if len(files)!=len(times) or len(files)<4:raise ValueError('insufficient frames or timestamp count mismatch')
    frames=[{'path':p.name,'timestamp_s':round(t,6),'sha256':digest(p)} for p,t in zip(files,times)]
    saved={'recipe':recipe,'frames':frames};atomic_json(receipt,saved)
    return receipt,saved


def subsample(frames,fps):
    result=[];last=-math.inf
    for f in frames:
        if f['timestamp_s']-last>=1/fps-.01:
            result.append(dict(f));last=f['timestamp_s']
    if result[-1]['timestamp_s']!=frames[-1]['timestamp_s']:result.append(dict(frames[-1]))
    while len(result)%4:result.append(dict(result[-1]))
    return result
