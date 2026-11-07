"""Frame-indexed compositor. Gradient plate cleanup adapted from Tejashmakwana (MIT)."""
import json
import math
import os
import subprocess
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont
from .media import probe
from .process import popen, run, Cancelled


def state_at(track, time):
    keys=track.keyframes
    if time<=keys[0].t:return keys[0].model_dump()
    if time>=keys[-1].t:return keys[-1].model_dump()
    for a,b in zip(keys,keys[1:]):
        if a.t<=time<=b.t:
            p=(time-a.t)/max(.00001,b.t-a.t)
            easing=getattr(track,'easing','linear')
            if easing=='smooth':p=p*p*(3-2*p)
            elif easing=='out':p=1-(1-p)**3
            elif easing=='step':p=0
            return {k:av+(getattr(b,k)-av)*p for k,av in a.model_dump().items()}
    return keys[-1].model_dump()


def clear_region(frame, box, method, color):
    height,width=frame.shape[:2]
    x0,y0,x1,y1=box
    x0=max(0,min(width-1,int(x0)));x1=max(0,min(width,int(x1)))
    y0=max(0,min(height-1,int(y0)));y1=max(0,min(height,int(y1)))
    if x1<=x0 or y1<=y0:return frame
    if method=='solid':frame[y0:y1,x0:x1]=ImageColor.getrgb(color)
    elif method=='gradient':
        # Original method: interpolate each column between rows outside the lettering.
        top=frame[max(0,y0-1):max(0,y0-1)+1,x0:x1].astype(float)
        bottom=frame[min(height-1,y1):min(height-1,y1)+1,x0:x1].astype(float)
        blend=np.linspace(0,1,y1-y0)[:,None,None]
        frame[y0:y1,x0:x1]=np.rint(top*(1-blend)+bottom*blend).clip(0,255).astype(np.uint8)
    else:
        pad=12;lx=max(0,x0-pad);ly=max(0,y0-pad);rx=min(width,x1+pad);ry=min(height,y1+pad)
        roi=frame[ly:ry,lx:rx];mask=np.zeros(roi.shape[:2],np.uint8)
        mask[y0-ly:y1-ly,x0-lx:x1-lx]=255
        frame[ly:ry,lx:rx]=cv2.inpaint(roi,mask,3,cv2.INPAINT_TELEA)
    return frame


DEJAVU_DIRS=('/usr/share/fonts/truetype/dejavu','/usr/share/fonts/dejavu','/usr/share/fonts/TTF')
FONT_FALLBACKS={
    ('sans','regular'):('DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf','/System/Library/Fonts/Helvetica.ttc'),
    ('sans','bold'):('DejaVuSans-Bold.ttf','/System/Library/Fonts/Supplemental/Arial Bold.ttf','/System/Library/Fonts/Helvetica.ttc'),
    ('serif','regular'):('DejaVuSerif.ttf','/System/Library/Fonts/Supplemental/Georgia.ttf','/System/Library/Fonts/Supplemental/Times New Roman.ttf'),
    ('serif','bold'):('DejaVuSerif-Bold.ttf','/System/Library/Fonts/Supplemental/Georgia Bold.ttf','/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'),
    ('mono','regular'):('DejaVuSansMono.ttf','/System/Library/Fonts/Supplemental/Courier New.ttf','/System/Library/Fonts/Menlo.ttc'),
    ('mono','bold'):('DejaVuSansMono-Bold.ttf','/System/Library/Fonts/Supplemental/Courier New Bold.ttf','/System/Library/Fonts/Menlo.ttc'),
}


def _font_paths(family,weight):
    for name in FONT_FALLBACKS[family,weight]:
        if name.startswith('/'):yield name
        else:
            for folder in DEJAVU_DIRS:yield f'{folder}/{name}'


@lru_cache(maxsize=256)
def font_for(family, weight, size):
    fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    name={'sans':('arial.ttf','arialbd.ttf'),'serif':('georgia.ttf','georgiab.ttf'),'mono':('consola.ttf','consolab.ttf')}[family][weight=='bold']
    path=fonts/name
    if path.exists():return ImageFont.truetype(str(path),max(1,size))
    for path in _font_paths(family,weight):
        if Path(path).exists():return ImageFont.truetype(path,max(1,size))
    return ImageFont.load_default(size=max(1,size))


@lru_cache(maxsize=8)
def gradient(width,height,color,color2):
    a=np.array(ImageColor.getrgb(color));b=np.array(ImageColor.getrgb(color2))
    blend=np.linspace(0,1,height)[:,None,None]
    return Image.fromarray(np.broadcast_to(np.uint8(a*(1-blend)+b*blend),(height,width,3)).copy()).convert('RGBA')


def draw_layer(base, track, t, logo=None):
    if not track.start<=t<track.end:return
    s=state_at(track,t)
    if s['opacity']<.001:return
    W,H=base.size
    # Render within bounded dimensions; reject huge allocations from model output.
    w=max(1,min(W*2,round(s['w']*W)));h=max(1,min(H*2,round(s['h']*H)))
    x=round(s['x']*W);y=round(s['y']*H)
    pad=min(80,round(s['blur']*3))
    layer=Image.new('RGBA',(w,h))
    draw=ImageDraw.Draw(layer)
    color=track.color
    if track.kind=='gradient':layer=gradient(w,h,track.color,track.color2).copy()
    elif track.kind=='text':
        text=track.text[:math.ceil(len(track.text)*s['reveal'])]
        size=max(2,round(track.size*H))
        # Fit the intended box without clipping longer replacement brands.
        font=font_for(track.font,track.weight,size)
        box=draw.multiline_textbbox((0,0),text,font=font,spacing=round(size*.18))
        ratio=min(1,w/max(1,box[2]-box[0]),h/max(1,box[3]-box[1]))
        font=font_for(track.font,track.weight,max(2,round(size*ratio)))
        box=draw.multiline_textbbox((0,0),text,font=font,spacing=round(size*ratio*.18))
        tw=box[2]-box[0];th=box[3]-box[1]
        tx={'left':0,'center':(w-tw)/2,'right':w-tw}[track.align]
        draw.multiline_text((tx-box[0],(h-th)/2-box[1]),text,font=font,fill=color,align=track.align,spacing=round(size*ratio*.18))
    elif track.kind=='image' and track.asset=='logo' and logo:
        im=logo.copy();im.thumbnail((w,h),Image.Resampling.LANCZOS);layer.alpha_composite(im,((w-im.width)//2,(h-im.height)//2))
    elif track.kind in ('rect','ellipse'):
        stroke=max(1,round(track.stroke*H))
        kwargs={'fill':None if track.stroke else color,'outline':color if track.stroke else None,'width':stroke}
        if track.kind=='rect':draw.rounded_rectangle((0,0,w-1,h-1),radius=min(w/2,h/2,track.radius*H),**kwargs)
        else:draw.ellipse((0,0,w-1,h-1),**kwargs)
    elif track.kind=='line':draw.line((0,0,w-1,h-1),fill=color,width=max(1,round(track.stroke*H)))
    if track.kind!='text' and s['reveal']<1:
        a=layer.getchannel('A');ImageDraw.Draw(a).rectangle((round(w*s['reveal']),0,w,h),fill=0);layer.putalpha(a)
    if pad:
        expanded=Image.new('RGBA',(w+pad*2,h+pad*2));expanded.alpha_composite(layer,(pad,pad))
        layer=expanded.filter(ImageFilter.GaussianBlur(s['blur']));x-=pad;y-=pad
    if abs(s['rotation'])>.01:
        before=layer.size;layer=layer.rotate(-s['rotation'],resample=Image.Resampling.BICUBIC,expand=True)
        x-=round((layer.width-before[0])/2);y-=round((layer.height-before[1])/2)
    if s['opacity']<1:layer.putalpha(layer.getchannel('A').point(lambda a:round(a*s['opacity'])))
    base.alpha_composite(layer,(x,y))


def render(folder, plan, brief, cancel, progress, *, preview=False):
    meta=json.loads((folder/'media.json').read_text(encoding='utf-8'))
    ratio=min(1,960/meta['width']) if preview else 1
    W=round(meta['width']*ratio/2)*2;H=round(meta['height']*ratio/2)*2
    # Preserve every source frame during review; dropping to 12 fps hid cut-boundary errors.
    fps=meta['fps']
    count=math.ceil(meta['duration']*fps)
    cap=cv2.VideoCapture(str(folder/'source.mp4'))
    logo=Image.open(folder/'logo.png').convert('RGBA') if (folder/'logo.png').exists() else None
    path=folder/('preview.mp4' if preview else 'output.mp4')
    temp=folder/('preview.pending.mp4' if preview else 'output.pending.mp4')
    args=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}',
          '-r',str(fps),'-i','pipe:0','-i',str(folder/'source.mp4'),'-map','0:v:0']
    if brief.keep_audio and meta['audio']:args+=['-map','1:a:0','-c:a','copy']
    args+=['-c:v','libx264','-preset','veryfast','-crf','20' if preview else '17','-pix_fmt','yuv420p',
           '-t',str(count/fps),'-movflags','+faststart',str(temp)]
    err_path=folder/'render-error.log'
    last_frame=-1;frame=None
    with err_path.open('wb') as errors:
        proc=popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        try:
            for i in range(count):
                if cancel.is_set():raise Cancelled()
                t=i/fps
                if brief.mode=='adapt':
                    target=min(round(t*meta['fps']),max(0,round(meta['duration']*meta['fps'])-1))
                    while last_frame<target:
                        ok,bgr=cap.read()
                        if not ok:break
                        frame=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);last_frame+=1
                    if frame is None:raise ValueError('Reference frame decode failed.')
                    rgb=cv2.resize(frame,(W,H)) if (frame.shape[1],frame.shape[0])!=(W,H) else frame.copy()
                    for mask in plan.masks:
                        if mask.start<=t<mask.end:
                            s=state_at(mask,t)
                            rgb=clear_region(rgb,(s['x']*W,s['y']*H,(s['x']+s['w'])*W,(s['y']+s['h'])*H),mask.method,mask.color)
                    image=Image.fromarray(rgb).convert('RGBA')
                else:image=Image.new('RGBA',(W,H),plan.background)
                for track in plan.tracks:draw_layer(image,track,t,logo)
                proc.stdin.write(image.convert('RGB').tobytes())
                if i%max(1,int(fps))==0:progress('Rendering preview' if preview else 'Rendering final video',round(48+i/count*16) if preview else round(78+i/count*18))
            proc.stdin.close()
            proc.wait(timeout=90)
            if proc.returncode:raise RuntimeError('Video encoding failed. See render-error.log in the project folder.')
        finally:
            cap.release()
            if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
    temp.replace(path)
    if not preview:
        progress('Verifying frames and audio',97)
        run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],timeout=120,cancel=cancel)
        actual=probe(path)
        frame_count=int(run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
                            'stream=nb_read_frames','-of','default=nw=1:nk=1',str(path)],timeout=120))
        if frame_count!=count:raise RuntimeError(f'Frame verification failed: expected {count}, got {frame_count}.')
        expected_audio=brief.keep_audio and meta['audio']
        if actual['audio']!=expected_audio:raise RuntimeError('Audio verification failed.')
        report={'decoded':True,'expected_frames':count,'actual_frames':frame_count,'audio_present':actual['audio'],
                'dimensions':[W,H],'fps':fps,'mode':brief.mode,'duration':actual['duration']}
        (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return path
