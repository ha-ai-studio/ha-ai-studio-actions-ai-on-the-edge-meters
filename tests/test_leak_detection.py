"""Synthetic consumption histories; no network or Home Assistant access."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1] / 'actions/water-leak-detection'
spec = importlib.util.spec_from_file_location('leak_action', ROOT / 'action.py')
leak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(leak)
SETTINGS = {'entity_id':'sensor.water', 'history_hours':8, 'minimum_rate_lph':1,
            'minimum_duration_hours':6, 'max_gap_minutes':60}


def history(values=None):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = values if values is not None else [100 + i * .002 for i in range(9)]
    return {'start':start.isoformat(), 'end':(start+timedelta(hours=8)).isoformat(),
            'readings':[{'state':str(v), 'timestamp':(start+timedelta(hours=i)).isoformat(),
                         'unit':'m³', 'state_class':'total_increasing'} for i,v in enumerate(values)]}


class AnalysisTests(unittest.TestCase):
    def test_sustained_and_normal(self):
        value=leak.analyze(history(), SETTINGS)
        self.assertEqual(value['status'], 'suspected_leak')
        self.assertEqual(value['total_liters'], 16)
        self.assertEqual(leak.analyze(history([100]*9), SETTINGS)['status'],'normal')
        self.assertEqual(leak.analyze(history([100,100,101,101,102,102,103,103,104]), SETTINGS)['status'],'normal')
    def test_invalid_data_never_means_normal(self):
        for change in ('reset','unknown','nan','gap','duplicate','unit','class','future','stale','negative','timezone','overflow'):
            with self.subTest(change=change):
                value=history();row=value['readings'][4]
                if change=='reset':row['state']='0'
                if change in ('unknown','nan'):row['state']=change
                if change=='negative':row['state']='-1'
                if change=='overflow':row['state']='1e999999999'
                if change=='gap':value['readings'].pop(4)
                if change=='duplicate':row['timestamp']=value['readings'][3]['timestamp']
                if change=='unit':row['unit']='L'
                if change=='class':row['state_class']='measurement'
                if change=='future':row['timestamp']='2099-01-01T00:00:00+00:00'
                if change=='stale':value['readings']=value['readings'][:-2]
                if change=='timezone':row['timestamp']='2026-01-01T04:00:00'
                self.assertEqual(leak.analyze(value,SETTINGS)['status'],'insufficient_data')
    def test_exact_threshold_decimal_readings(self):
        value=history()
        for i,row in enumerate(value['readings']):row['state']=f'{1+i/1000:.6f}'
        self.assertEqual(leak.analyze(value,SETTINGS)['status'],'suspected_leak')
        value['readings'][4]['timestamp']=None
        self.assertEqual(leak.analyze(value,SETTINGS)['status'],'insufficient_data')

    def test_missing_and_short_history(self):
        for readings in ([], history()['readings'][:3]):
            value=history();value['readings']=readings
            self.assertEqual(leak.analyze(value,SETTINGS)['status'],'insufficient_data')
    def test_liters_and_duration(self):
        value=history()
        for row in value['readings']:row['unit']='L';row['state']=str(float(row['state'])*1000)
        self.assertEqual(leak.analyze(value,SETTINGS)['status'],'suspected_leak')
        self.assertEqual(leak.analyze(value,{**SETTINGS,'minimum_duration_hours':9})['status'],'insufficient_data')
    def test_api_failure_safe_result(self):
        class Client:
            def history(self,*args):raise ValueError('private-token')
        value=leak.execute({},SETTINGS,context={'home_assistant':Client()})
        self.assertEqual(value['status'],'insufficient_data')
        self.assertNotIn('private-token',json.dumps(value))
