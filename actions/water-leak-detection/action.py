"""Conservative, deterministic leak suspicion from recorded cumulative readings.

No model or external service receives the household's consumption history.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math

UNITS = {'m³': 1000, 'm3': 1000, 'L': 1, 'l': 1}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('History timestamp is missing.')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('History timestamps must include a timezone.')
    return parsed.timestamp()


def result(status, reason, **metrics):
    return {'status': status, 'reason': reason, 'method': 'interval_pattern', **metrics,
            'readings': [{'id': 'leak-status', 'status': 'read', 'value': status},
                         {'id': 'leak-reason', 'status': 'read', 'value': reason}]}


def analyze(history, settings):
    def insufficient(reason):
        return result('insufficient_data', reason)
    rows = history.get('readings', [])
    if len(rows) < 4:
        return insufficient('At least four recorded cumulative readings are required.')
    gap = settings['max_gap_minutes'] * 60
    minimum = settings['minimum_duration_hours'] * 3600
    threshold = Decimal(str(settings['minimum_rate_lph']))
    if minimum > settings['history_hours'] * 3600:
        return insufficient('The history period must cover the minimum suspicion duration.')
    try:
        start, end = timestamp(history['start']), timestamp(history['end'])
        if not start < end:
            raise ValueError()
        points = []
        units = set()
        classes = set()
        for row in rows:
            value = Decimal(str(row['state']))
            when = timestamp(row['timestamp'])
            unit = row['unit']
            if isinstance(row['state'], bool) or not value.is_finite() or not 0 <= value <= Decimal('1e100') or unit not in UNITS:
                raise ValueError()
            if row['state_class'] not in ('total', 'total_increasing') or not start <= when <= end:
                raise ValueError()
            units.add(unit);classes.add(row['state_class'])
            points.append((when, value * UNITS[unit]))
        if len(units) != 1 or len(classes) != 1:
            return insufficient('The sensor unit or state class changed during the selected period.')
    except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation):
        return insufficient('History contains unavailable, invalid, or unsupported cumulative readings. Use a total sensor in L or m³.')
    # Do not sort or silently drop bad records: that could hide resets or gaps.
    if points[0][0] - start > gap or end - points[-1][0] > gap:
        return insufficient('History does not cover the selected period with recent readings.')
    longest = duration = 0.0
    count = streak_count = 0
    total = Decimal(0)
    for (previous_time, previous), (when, value) in zip(points, points[1:]):
        elapsed, delta = when - previous_time, value - previous
        if elapsed <= 0 or elapsed > gap:
            return insufficient('History contains duplicate timestamps, unordered readings, or a measurement gap.')
        if delta < 0:
            return insufficient('A counter reset or decreasing reading prevents a reliable assessment.')
        rate = delta * 3600 / Decimal(str(elapsed))
        if not math.isfinite(rate) or not math.isfinite(total + delta):
            return insufficient('History values exceed the supported numeric range.')
        total += delta
        if rate >= threshold:
            duration += elapsed;streak_count += 1
            if streak_count >= 3:
                longest = max(longest, duration)
        else:
            duration = 0;streak_count = 0
        count += 1
    if points[-1][0] - points[0][0] < minimum:
        return insufficient('The recorded readings span less than the minimum suspicion duration.')
    suspected = longest >= minimum
    reason = ('Repeated consumption across consecutive recorded intervals suggests a possible leak. '
              'Interval averages do not prove uninterrupted flow.' if suspected else
              'No sustained consumption pattern met the configured thresholds. This does not rule out a leak.')
    return result('suspected_leak' if suspected else 'normal', reason,
                  total_liters=round(float(total), 3), evaluated_intervals=count,
                  longest_suspicious_hours=round(longest / 3600, 3))


def execute(data, settings, *, context):
    try:
        history = context['home_assistant'].history(settings['entity_id'], settings['history_hours'])
    except ValueError:
        return result('insufficient_data', 'Sensor history could not be read. Check the Home Assistant connection and recorder availability.')
    return analyze(history, settings)
