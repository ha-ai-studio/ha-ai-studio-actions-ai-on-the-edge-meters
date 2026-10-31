"""Bounded image loading, two-anchor alignment and upstream TFLite inference.

Inference decoding and pointer correction adapted from AI-on-the-edge-device.
See THIRD_PARTY.md for original sources and modifications.
"""
from io import BytesIO
from copy import deepcopy
import math
import hashlib
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import warnings
import numpy as np
from PIL import Image, ImageOps
import cv2
from correction import combine
from number_block import recognize as recognize_number_block
from report import Report

Image.MAX_IMAGE_PIXELS = 16_000_000
MAX_BYTES = 8 * 1024 * 1024
ID = re.compile(r'[a-f0-9]{64}\.(png|jpg)')
MODEL_ROOT = Path(__file__).parent / 'models'


class ReadingError(ValueError):
    pass


def decode(content):
    if len(content) > MAX_BYTES:
        raise ReadingError('Image exceeds 8 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened:
                if opened.format not in ('PNG', 'JPEG') or opened.width * opened.height > 16_000_000 or max(opened.size) > 8192:
                    raise ReadingError('Use a PNG or JPEG image up to 16 megapixels.')
                image = ImageOps.exif_transpose(opened).convert('RGB')
                image.load()
                return image
    except ReadingError:
        raise
    except Exception:
        raise ReadingError('Image could not be decoded.') from None


def asset(ident, context):
    if not isinstance(ident, str) or not ID.fullmatch(ident):
        raise ReadingError('Select a valid uploaded image.')
    root = Path(context['assets_dir']).resolve()
    path = root / ident
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root) or path.stat().st_size > MAX_BYTES:
        raise ReadingError('Uploaded image is unavailable.')
    return decode(path.read_bytes())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ReadingError('Image URL redirects are not allowed.')


def source(data, settings, context):
    value = data.get('image', {})
    if 'asset_id' in value:
        return asset(value['asset_id'], context)
    if context.get('mode') == 'preview':
        raise ReadingError('Preview uses uploaded images only; network access is disabled.')
    url = value.get('url')
    if not isinstance(url,str) or not url:
        raise ReadingError('Supply an image URL in image.url.')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ReadingError('Supply an HTTP(S) image URL without embedded credentials.')
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(url, timeout=5) as response:
            return decode(response.read(MAX_BYTES + 1))
    except ReadingError:
        raise
    except Exception:
        raise ReadingError('Image download failed. Check image.url in the request.') from None


def rotated(image, rotation):
    return image.rotate(-rotation, expand=True)


def straighten(image, degrees):
    if not isinstance(degrees,(int,float)) or not math.isfinite(degrees) or abs(degrees)>180:
        raise ReadingError('Straighten angle must be between -180 and 180 degrees.')
    mask=np.ones((image.height,image.width),dtype=np.float32)
    if not degrees:return image,mask
    # Canvas uses clockwise angles around edge coordinates; OpenCV uses pixel centers.
    matrix=cv2.getRotationMatrix2D(((image.width-1)/2,(image.height-1)/2),-degrees,1)
    pixels=cv2.warpAffine(np.asarray(image),matrix,image.size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    mask=cv2.warpAffine(mask,matrix,image.size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    return Image.fromarray(pixels),mask


def box(roi, size):
    x,y,w,h = (roi[k] for k in ('x','y','width','height'))
    if any(type(v) is not int for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<4 or x+w>size[0] or y+h>size[1]:
        raise ReadingError('A region lies outside the image or is smaller than 4 pixels.')
    return x,y,x+w,y+h


def align(image, reference, anchors, search, threshold, valid_regions=(), input_validity=None):
    if image.size != reference.size:
        raise ReadingError('Test/request image dimensions must match the reference image after orientation.')
    if len(anchors) != 2:
        raise ReadingError('Draw exactly two alignment reference regions.')
    current = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    original = cv2.cvtColor(np.asarray(reference), cv2.COLOR_RGB2GRAY)
    targets=[];found=[];scores=[]
    for roi in anchors:
        x,y,right,bottom = box(roi, reference.size)
        template=original[y:bottom,x:right]
        if float(template.std()) < 3:
            raise ReadingError('Alignment reference is too uniform. Select a distinctive mark.')
        sx,sy=max(0,x-search),max(0,y-search)
        window=current[sy:min(current.shape[0],bottom+search),sx:min(current.shape[1],right+search)]
        matches=cv2.matchTemplate(window,template,cv2.TM_CCOEFF_NORMED)
        _,score,_,position=cv2.minMaxLoc(matches)
        if not math.isfinite(score) or score < threshold:
            raise ReadingError('Alignment reference was not found confidently.')
        if input_validity is not None:
            mx,my=sx+position[0],sy+position[1]
            if np.any(input_validity[my:my+bottom-y,mx:mx+right-x]<.999999):
                raise ReadingError('Matched alignment reference overlaps an empty corner created by straightening.')
        half=np.array([(right-x)/2,(bottom-y)/2])
        targets.append(np.array([x,y])+half);found.append(np.array([sx+position[0],sy+position[1]])+half);scores.append(float(score))
    a,b=found;ta,tb=targets
    delta=b-a;target=tb-ta
    if np.linalg.norm(delta)<10 or np.linalg.norm(target)<10:
        raise ReadingError('Alignment reference regions must be farther apart.')
    # Rigid transform: translation and rotation; reject scale changes.
    ratio=float(np.linalg.norm(delta)/np.linalg.norm(target))
    if not .95<=ratio<=1.05:
        raise ReadingError('Alignment reference spacing changed too much.')
    angle=math.atan2(target[1],target[0])-math.atan2(delta[1],delta[0])
    angle=math.atan2(math.sin(angle),math.cos(angle))
    if abs(angle)>math.radians(15):
        raise ReadingError('Image rotation exceeds the alignment limit.')
    matrix=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    offset=(ta+tb)/2-matrix@((a+b)/2)
    affine=np.column_stack((matrix,offset))
    result=cv2.warpAffine(np.asarray(image),affine,reference.size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    validity=cv2.warpAffine(np.ones((image.height,image.width),dtype=np.float32) if input_validity is None else input_validity,affine,reference.size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    for roi in valid_regions:
        x,y,right,bottom=box(roi,reference.size)
        if np.any(validity[y:bottom,x:right]<.999999):
            raise ReadingError('Alignment moves a reading region beyond the available image. Expand the crop or use a better aligned input image.')
    return Image.fromarray(result),{'scores':scores,'rotation_degrees':math.degrees(angle),'translation':offset.tolist()}


class Models:
    def __init__(self):
        self.models={}
    def read(self,image,kind,ccw,threshold):
        from ai_edge_litert.interpreter import Interpreter
        if kind not in self.models:
            filename='ana-cont_1500_s2_q.tflite' if kind=='analog' else 'dig-cont_0900_s3_q.tflite'
            interpreter=Interpreter(model_path=str(MODEL_ROOT/filename),num_threads=1)
            interpreter.allocate_tensors();self.models[kind]=interpreter
        interpreter=self.models[kind]
        spec=interpreter.get_input_details()[0];out=interpreter.get_output_details()[0]
        _,height,width,channels=spec['shape']
        if channels!=3:raise ReadingError('Model has unsupported input channels.')
        # Upstream feeds RGB pixels in [0,255], not normalized RGB.
        pixels=np.asarray(image.resize((int(width),int(height)),Image.Resampling.BILINEAR),dtype=np.float32)[None,...]
        if np.issubdtype(spec['dtype'],np.integer):
            scale,zero=spec['quantization'];pixels=np.clip(np.rint(pixels/scale+zero),np.iinfo(spec['dtype']).min,np.iinfo(spec['dtype']).max)
        interpreter.set_tensor(spec['index'],pixels.astype(spec['dtype']));interpreter.invoke()
        values=interpreter.get_tensor(out['index']).reshape(-1).astype(float)
        if np.issubdtype(out['dtype'],np.integer):
            scale,zero=out['quantization'];values=(values-zero)*scale
        if not np.isfinite(values).all():raise ReadingError('Model returned non-finite values.')
        if kind=='analog' and len(values)==2:
            raw=(math.atan2(values[0],values[1])/(2*math.pi))%1*10
            # Vector magnitude is a fit diagnostic, not a calibrated probability.
            fit=min(1.,float(np.linalg.norm(values)))
        elif kind=='digit' and len(values)==10:
            index=int(values.argmax());plus=(index+1)%10;minus=(index-1)%10
            neighbor=plus if values[plus]>values[minus] else minus
            fit=float(values[index]+values[neighbor])
            if fit<=0:raise ReadingError('Digit model could not classify the region.')
            raw=(index+(1 if neighbor==plus else -1)*values[neighbor]/fit)%10
        else:raise ReadingError('Model output shape is unsupported.')
        if ccw and kind=='analog':raw=(10-raw)%10
        return float(raw),max(0.,min(1.,fit)),bool(fit>=threshold)


def crop_inputs(image, reference, rois, crop):
    if image.size != reference.size:
        raise ReadingError('Test/request image dimensions must match the reference image after orientation.')
    if crop is None:
        return image, reference, rois
    bounds = box(crop, reference.size)
    translated = []
    for roi in rois:
        shifted = {**roi, 'x': roi['x'] - crop['x'], 'y': roi['y'] - crop['y']}
        try:
            box(shifted, (crop['width'], crop['height']))
        except ReadingError as exc:
            raise ReadingError('Crop must include all alignment and reading regions.') from exc
        translated.append(shifted)
    return image.crop(bounds), reference.crop(bounds), translated


def resolve_layouts(settings):
    settings=deepcopy(settings)
    rois=settings.get('regions',[])
    by_id={r['id']:r for r in rois}
    meters=settings.get('meters',[])
    if len(by_id)!=len(rois) or len({m['id'] for m in meters})!=len(meters):
        raise ReadingError('Region and meter IDs must be unique.')
    layout_meters={m['id'] for m in meters if 'layout' in m}
    if not layout_meters:return settings
    for r in rois:
        if r.get('meter') in layout_meters:r.pop('meter',None)
    used={r['id'] for r in rois if r.get('meter')}
    for m in meters:
        if 'layout' not in m:continue
        # Explicit frame mapping is authoritative, including for saved configurations.
        m['extended_resolution']=False
        tokens=m['layout'];frames=[token for token in tokens if token!=',']
        if not frames:raise ReadingError('Add at least one frame to every value.')
        if tokens.count(',')>1 or len(frames)!=len(set(frames)) or len(frames)>15:
            raise ReadingError('Use up to 15 unique frames and one comma per value.')
        blocks=[ident for ident in frames if by_id.get(ident,{}).get('kind')=='number_block']
        if blocks and (len(tokens)!=1):
            raise ReadingError('A Number block must be the only pill in its value, without a comma.')
        analog_seen=False;counts={'digit':0,'analog':0,'number_block':0}
        for ident in frames:
            r=by_id.get(ident)
            if not r or r.get('kind') not in counts:raise ReadingError('Choose Digit, Analog dial or Number block for every frame used in a value.')
            if ident in used:raise ReadingError('A frame can belong to only one value.')
            used.add(ident)
            if r['kind']=='analog':analog_seen=True
            elif analog_seen:raise ReadingError('Place mechanical digits before analog dials for transition correction.')
            r['meter']=m['id'];r['order']=counts[r['kind']];counts[r['kind']]+=1
        integer_places=tokens.index(',') if ',' in tokens else len(frames)
        m['decimal_shift']=0 if blocks else integer_places-counts['digit']
    settings['regions']=[r for r in rois if r['kind']=='alignment' or r['id'] in used]
    return settings


def prepare_crop(image, mode):
    if mode == 'none':return image
    if mode == 'autocontrast':return ImageOps.autocontrast(image)
    if mode == 'grayscale_autocontrast':return ImageOps.autocontrast(image.convert('L')).convert('RGB')
    raise ReadingError('Unknown image preprocessing mode.')


def read_model_region(image, roi, settings, models, report=None):
    kind=roi['kind'];threshold=settings.get(kind+'_threshold',settings.get('recognition_threshold',.5))
    mode=settings.get(kind+'_preprocessing','none')
    variants=[]
    offsets=[(0,0),(-2,0),(2,0),(0,-2),(0,2)] if settings.get('stability_check',False) else [(0,0)]
    raw=fit=None
    for dx,dy in offsets:
        shifted={**roi,'x':roi['x']+dx,'y':roi['y']+dy}
        try:bounds=box(shifted,image.size)
        except ReadingError:
            return raw,fit,False,'Stability check needs a two-pixel margin around this frame.',variants
        prepared=prepare_crop(image.crop(bounds),mode)
        value,score,accepted=models.read(prepared,kind,roi.get('ccw',False),threshold)
        if report:report.add(f"{roi.get('name',roi['id'])}: model ({dx}, {dy})", prepared.resize((32,32), Image.Resampling.BILINEAR), f'{mode} | raw={value:.4f} | fit={score:.4f} | minimum={threshold} | accepted={accepted}')
        variants.append({'dx':dx,'dy':dy,'raw':value,'fit':score})
        if dx==dy==0:raw,fit=value,score
        if not accepted:
            return raw,fit,False,'Model fit is below the configured threshold'+(' in a shifted crop.' if dx or dy else '.'),variants
        # Circular distance preserves the 9 -> 0 transition. Do not round away
        # the fractional values needed by upstream digit/dial correction.
        distance=abs(value-raw)
        if min(distance,10-distance)>.25:
            return raw,fit,False,'Unstable frame: shifting the crop by two pixels changes the reading by more than 0.25 digit positions.',variants
    return raw,fit,True,None,variants


def run(data,settings,context,preview=False):
    deadline=time.monotonic()+20
    first=source(data,settings,context)
    needs_confirmation=settings.get('require_confirmation',False)
    second=None
    if 'confirmation_image' in data:
        second=source({'image':data['confirmation_image']},settings,context)
        if first.size==second.size and hashlib.sha256(first.tobytes()).digest()==hashlib.sha256(second.tobytes()).digest():
            raise ReadingError('Confirmation needs a different capture; the two decoded images are identical.')
    elif needs_confirmation and not preview:
        raise ReadingError('Supply confirmation_image from a second capture to confirm this reading.')
    report=Report() if preview else None
    result=run_single(data,settings,context,preview,first,deadline,report)
    if second is not None:
        other=run_single(data,settings,context,False,second,deadline,report)
        for reading,confirmation in zip(result['readings'],other['readings']):
            if reading['status']=='read' and (confirmation['status']!='read' or reading['value']!=confirmation['value']):
                reading.update(status='unreadable',value=None,reason='The second capture is unreadable or does not agree with this value.')
            reading['confirmation']='passed' if reading['status']=='read' else 'failed'
        result['status']='read' if all(r['status']=='read' for r in result['readings']) else 'unreadable'
    elif needs_confirmation:
        for reading in result['readings']:
            reading['confirmation']='not_tested'
            if reading['status']=='read':reading.update(status='unreadable',value=None,reason='Reference-only preview: a second capture is required for confirmation.')
        result['status']='unreadable'
        result['message']='Reference diagnostics completed. Multi-image confirmation was not tested.'
    if report:report.save(Path(context['output_dir'])/'recognition-report.jpg',result)
    return result


def run_single(data,settings,context,preview,image,deadline,report=None):
    if report:report.add("Input image" if preview else "Confirmation input",image)
    settings=resolve_layouts(settings)
    reference_spec=settings.get('reference')
    rois=settings.get('regions',[]);meters=settings.get('meters',[])
    if not reference_spec or not rois or not meters:
        raise ReadingError('Upload a reference image, define two alignment regions and configure at least one meter.')
    if any(roi.get('kind') == 'unassigned' for roi in rois):
        raise ReadingError('Choose a type for every frame in Region properties.')
    reference=asset(reference_spec['asset_id'],context)
    rotation=settings.get('rotation',0)
    reference=rotated(reference,rotation);image=rotated(image,rotation)
    if report:report.add("Quarter-turn rotation",image,f"Rotation: {rotation} degrees")
    reference,reference_mask=straighten(reference,settings.get('straighten_angle',0))
    image,image_mask=straighten(image,settings.get('straighten_angle',0))
    if report:report.add('Straightening',image,f"Correction: {settings.get('straighten_angle',0)} degrees")
    ids=[r['id'] for r in rois];meter_ids=[m['id'] for m in meters]
    if len(set(ids))!=len(ids) or len(set(meter_ids))!=len(meter_ids):raise ReadingError('Region and meter IDs must be unique.')
    for roi in rois:
        box(roi,reference.size)
        if roi['kind']!='alignment' and roi.get('meter') not in meter_ids:raise ReadingError('Assign every reading region to a meter.')
    crop=settings.get('crop')
    if crop:
        x,y,right,bottom=box(crop,reference.size)
        reference_mask=reference_mask[y:bottom,x:right];image_mask=image_mask[y:bottom,x:right]
    image,reference,rois=crop_inputs(image,reference,rois,crop)
    if report:report.add('Crop',image,str(crop) if crop else 'Full image; no crop configured')
    valid_regions=[r for r in rois if r['kind']!='alignment']
    if settings.get('stability_check',False):
        valid_regions=[{**r,'x':r['x']-2,'y':r['y']-2,'width':r['width']+4,'height':r['height']+4} if r['kind']!='number_block' else r for r in valid_regions]
        for r in valid_regions:
            try:box(r,reference.size)
            except ReadingError:raise ReadingError('Stability check needs a two-pixel margin around each digit/dial frame inside the crop.') from None
    anchors=[r for r in rois if r['kind']=='alignment']
    for r in [*anchors,*valid_regions]:
        x,y,right,bottom=box(r,reference.size)
        if np.any(reference_mask[y:bottom,x:right]<.999999):
            raise ReadingError('A frame overlaps an empty corner created by straightening. Move or resize the frame.')
    image,alignment=align(image,reference,anchors,settings.get('search_radius',40),settings.get('alignment_threshold',.7),valid_regions,image_mask)
    if report:
        report.add('Alignment',image,str(alignment))
        for anchor in anchors:report.add('Alignment reference: '+anchor.get('name',anchor['id']),reference.crop(box(anchor,reference.size)),f"Minimum match: {settings.get('alignment_threshold',.7)}")
    output=Path(context['output_dir']) if preview else None
    if output:image.save(output/'aligned.jpg',quality=85)
    models=Models();regions=[];ocr_deadline=deadline
    for index,roi in enumerate(rois):
        if roi['kind']=='alignment':continue
        crop=image.crop(box(roi,image.size))
        if output:crop.save(output/f'region-{index}.jpg',quality=90)
        if report:report.add(roi.get('name',roi['id'])+': original crop',crop,roi['kind'])
        reason=None;variants=[]
        if time.monotonic()>deadline:raise ReadingError('Recognition time budget exceeded. Reduce the number of regions or checks.')
        if roi['kind']=='number_block':
            fit=None
            try:
                raw=recognize_number_block(crop,roi.get('expected_length'),roi.get('expected_value'),deadline=ocr_deadline,trace=(lambda title,img,details:report.add(roi.get('name',roi['id'])+': '+title,img,details)) if report else None)
                accepted=True
            except ValueError as error:
                raw=None;accepted=False;reason=str(error)
        else:
            raw,fit,accepted,reason,variants=read_model_region(image,roi,settings,models,report)
        regions.append({'id':roi['id'],'meter':roi['meter'],'kind':roi['kind'],'order':roi['order'],'raw':raw,'fit':fit,'accepted':accepted,'reason':reason,'variants':variants,'image':f'region-{index}.jpg' if preview else None})
    readings=[]
    for meter in meters:
        selected=[r for r in regions if r['meter']==meter['id']]
        digits=sorted([r for r in selected if r['kind']=='digit'],key=lambda r:r['order'])
        pointers=sorted([r for r in selected if r['kind']=='analog'],key=lambda r:r['order'])
        blocks=[r for r in selected if r['kind']=='number_block']
        reason=None;value=None;raw_value=None
        try:
            if not selected:raise ReadingError('No regions assigned to this meter.')
            if blocks:
                if len(selected)!=1 or ',' in meter.get('layout',[]) or meter.get('decimal_shift',0):
                    raise ReadingError('A Number block must be the only pill in its value, without a comma or decimal shift.')
                if meter.get('extended_resolution') or meter.get('allow_negative') or 'max_change' in meter or 'max_rate' in meter or 'rate_tolerance' in meter or meter['id'] in data.get('previous',{}):
                    raise ReadingError('Number blocks return text. Remove numeric reading checks and previous readings for this value.')
                if not blocks[0]['accepted']:raise ReadingError(blocks[0]['reason'])
                raw_value=value=blocks[0]['raw']
                readings.append({'id':meter['id'],'name':meter.get('name',meter['id']),'unit':meter.get('unit',''),'status':'read','value':value,'raw_value':raw_value,'reason':None})
                continue
            if len(selected)+bool(meter.get('extended_resolution'))>15:raise ReadingError('Limit each meter to 15 significant positions, including extended resolution.')
            rejected=[r for r in selected if not r['accepted']]
            if rejected:raise ReadingError(f"Frame {rejected[0]['id']}: {rejected[0]['reason']}")
            if 'rate_tolerance' in meter and 'max_rate' not in meter:raise ReadingError('Rate tolerance requires a maximum rate per minute.')
            if any(len({r['order'] for r in rows})!=len(rows) for rows in (digits,pointers)):raise ReadingError('Region order must be unique within each meter and region type.')
            raw_value=combine([r['raw'] for r in digits],[r['raw'] for r in pointers],meter.get('decimal_shift',0),meter.get('extended_resolution',False),meter.get('transition_start',9.2))
            if settings.get('stability_check',False):
                for position in range(1,5):
                    candidate=combine([r['variants'][position]['raw'] for r in digits],[r['variants'][position]['raw'] for r in pointers],meter.get('decimal_shift',0),meter.get('extended_resolution',False),meter.get('transition_start',9.2))
                    if candidate!=raw_value:
                        for r in selected:
                            if r['variants'][position]['raw']!=r['raw']:
                                r.update(accepted=False,reason='Shifted crop changes the corrected meter value. Check this frame and neighboring positions.')
                        raise ReadingError('Frame stability failed: shifted crops do not agree after digit/dial correction.')
            value=float(raw_value)
            previous=data.get('previous',{}).get(meter['id'])
            if previous:
                delta=value-previous['value']
                if delta<0 and not meter.get('allow_negative',False):raise ReadingError('Reading decreased relative to the supplied previous value.')
                if 'max_change' in meter and abs(delta)>meter['max_change']:raise ReadingError('Reading exceeds the configured maximum change.')
                if 'max_rate' in meter:
                    elapsed=previous.get('elapsed_seconds',0)
                    if elapsed<=0:raise ReadingError('A positive elapsed_seconds is required for rate checking.')
                    if abs(delta)>meter['max_rate']*elapsed/60+meter.get('rate_tolerance',0):raise ReadingError('Reading exceeds the configured rate per minute plus tolerance.')
            elif 'max_change' in meter or 'max_rate' in meter:
                raise ReadingError('Supply a previous reading to apply configured change/rate checks.')
        except ValueError as error:
            reason=str(error);value=None
        readings.append({'id':meter['id'],'name':meter.get('name',meter['id']),'unit':meter.get('unit',''),'status':'read' if value is not None else 'unreadable','value':value,'raw_value':raw_value,'reason':reason})
    if report:
        for r in regions:report.add('Region result: '+r['id'],details=f"raw={r['raw']} | fit={r['fit']} | accepted={r['accepted']} | {r['reason'] or 'Checks passed'}")
    return {'status':'read' if all(r['status']=='read' for r in readings) else 'unreadable','readings':readings,'regions':regions,'alignment':alignment,'message':None}
