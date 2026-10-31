"""HA AI Studio Action: private images, upstream meter models, isolated preview."""
from engine import run, ReadingError


def execute(data, settings, *, context=None):
    try:
        return run(data,settings,context or {})
    except ReadingError as error:
        return {'status':'unreadable','readings':[],'regions':[],'alignment':None,'message':str(error)}


def preview(data, settings, *, context):
    # The preview implementation accepts only uploaded files, never remote URLs.
    try:
        return run(data,settings,{**context,'mode':'preview'},preview=True)
    except ReadingError as error:
        return {'status':'unreadable','readings':[],'regions':[],'alignment':None,'message':str(error)}
