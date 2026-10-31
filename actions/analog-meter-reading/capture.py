"""Action-owned acquisition sequence through Studio's credential-free HA client."""
import time
from engine import decode, ReadingError


def capture(settings, context):
    config=settings.get('capture',{})
    camera=config.get('camera_entity');light=config.get('light_entity')
    ha=context.get('home_assistant')
    if not ha or not camera:raise ReadingError('Configure a camera entity and a Home Assistant connection, or supply image in the request.')
    count=config.get('count',2 if settings.get('require_confirmation') else 1)
    delay=config.get('settle_seconds',2);interval=config.get('interval_seconds',1)
    if type(count) is not int or count not in (1,2):raise ReadingError('Choose one or two camera captures.')
    if settings.get('require_confirmation') and count!=2:raise ReadingError('Two matching captures requires two camera images.')
    if any(type(n) not in (int,float) or not 0<=n<=20 for n in (delay,interval)):raise ReadingError('Capture delays must be between 0 and 20 seconds.')
    discard=config.get('discard_first',False)
    if type(discard) is not bool:raise ReadingError('Discard first camera image must be a boolean.')
    try:
        ha.state(camera)
        if light:ha.light_on(light)
        if callable(getattr(ha,'report_wait',None)):ha.report_wait(camera,'before_capture',delay)
        time.sleep(delay)
        if discard:
            ha.capture(camera)  # Warm up the camera; never use this frame for recognition.
            if callable(getattr(ha,'report_wait',None)):ha.report_wait(camera,'between_captures',interval)
            time.sleep(interval)
        images=[decode(ha.capture(camera))]
        if count==2:
            if callable(getattr(ha,'report_wait',None)):ha.report_wait(camera,'between_captures',interval)
            time.sleep(interval);images.append(decode(ha.capture(camera)))
        return images
    except ReadingError:raise
    except ValueError as error:raise ReadingError(str(error)) from None
    finally:
        if light:
            try:ha.restore(light)
            except Exception:raise ReadingError('Light restoration failed. Studio will retry; check the illumination entity.') from None
