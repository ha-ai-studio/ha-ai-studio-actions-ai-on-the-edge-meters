"""HA AI Studio Action: private images, upstream meter models, isolated preview."""
from engine import run, ReadingError
from capture import capture


def execute(data, settings, *, context=None):
    try:
        if (context or {}).get('mode')=='reference_capture':
            from pathlib import Path
            images=capture(settings,context)
            for index,image in enumerate(images):image.save(Path(context['output_dir'])/f'reference-{index+1}.png')
            return {'status':'read','readings':[],'regions':[],'alignment':None,'message':'Reference images captured.'}
        return run(data,settings,context or {},preview=(context or {}).get('mode')=='camera_test',captured_images=capture(settings,context or {}) if 'image' not in data else None)
    except ReadingError as error:
        return {'status':'unreadable','readings':[],'regions':[],'alignment':None,'message':str(error)}


def preview(data, settings, *, context):
    # The preview implementation accepts only uploaded files, never remote URLs.
    try:
        return run(data,settings,{**context,'mode':'preview'},preview=True)
    except ReadingError as error:
        return {'status':'unreadable','readings':[],'regions':[],'alignment':None,'message':str(error)}
