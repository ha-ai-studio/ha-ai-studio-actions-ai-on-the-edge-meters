import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'actions/analog-meter-reading'))
from capture import capture
from engine import ReadingError
import action

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.ha=Mock();self.ha.capture.side_effect=[b'one',b'two'];self.context={'home_assistant':self.ha}
        self.settings={'capture':{'camera_entity':'camera.meter','light_entity':'light.meter','settle_seconds':2,'interval_seconds':1,'count':2}}
    def test_sequence_delays_restore_before_recognition(self):
        with patch('capture.decode',side_effect=lambda x:x),patch('capture.time.sleep') as sleep:
            self.assertEqual(capture(self.settings,self.context),[b'one',b'two'])
        self.assertEqual([c[0] for c in self.ha.mock_calls],['state','light_on','report_wait','capture','report_wait','capture','restore'])
        self.assertEqual([c.args for c in sleep.call_args_list],[(2,),(1,)])
        self.assertEqual([c.args for c in self.ha.report_wait.call_args_list],[('camera.meter','before_capture',2),('camera.meter','between_captures',1)])
    def test_capture_failure_restores_light(self):
        self.ha.capture.side_effect=ValueError('Camera unavailable')
        with patch('capture.time.sleep'),self.assertRaisesRegex(ReadingError,'Camera unavailable'):capture(self.settings,self.context)
        self.ha.restore.assert_called_once_with('light.meter')
    def test_invalid_count_and_delay_do_not_touch_devices(self):
        for change in ({'count':3},{'settle_seconds':float('nan')},{'interval_seconds':21}):
            with self.subTest(change=change),self.assertRaises(ReadingError):capture({'capture':{**self.settings['capture'],**change}},self.context)
        self.assertFalse(self.ha.mock_calls)
    def test_reference_preview_never_captures(self):
        with patch('action.run',return_value={'status':'read'}) as run,patch('action.capture') as acquire:
            action.preview({'image':{'asset_id':'synthetic'}},self.settings,context=self.context)
            acquire.assert_not_called();self.assertTrue(run.call_args.kwargs['preview'])
    def test_empty_request_captures_but_supplied_image_does_not(self):
        with patch('action.run',return_value={'status':'read'}) as run,patch('action.capture',return_value=['image']) as acquire:
            action.execute({},self.settings,context=self.context);acquire.assert_called_once()
            self.assertEqual(run.call_args.kwargs['captured_images'],['image'])
            acquire.reset_mock();action.execute({'image':{'url':'https://example.invalid/image'}},self.settings,context=self.context);acquire.assert_not_called()

    def test_captured_images_through_real_engine(self):
        from io import BytesIO
        from engine import Models
        from test_analog_meter_reading import EngineTests
        fixture=EngineTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        settings={**fixture.settings,**self.settings}
        first=BytesIO();fixture.image.save(first,format='PNG')
        other=fixture.image.copy();other.putpixel((630,470),(0,0,0));second=BytesIO();other.save(second,format='PNG')
        for captures,values,expected in [([first.getvalue(),second.getvalue()],[7.,5.,7.,5.],'read'),([first.getvalue(),second.getvalue()],[7.,5.,8.,5.],'unreadable'),([first.getvalue()]*2,[],'unreadable')]:
            ha=Mock();ha.capture.side_effect=captures
            with patch('capture.time.sleep'),patch.object(Models,'read',side_effect=[(v,1,True) for v in values]):
                result=action.execute({},settings,context={**fixture.context,'mode':'execute','home_assistant':ha})
            self.assertEqual(result['status'],expected);ha.restore.assert_called_once_with('light.meter')

    def test_camera_test_captures_and_generates_diagnostics(self):
        with patch('action.run',return_value={'status':'read'}) as run,patch('action.capture',return_value=['image']) as acquire:
            action.execute({},self.settings,context={**self.context,'mode':'camera_test','output_dir':'synthetic'})
            acquire.assert_called_once();self.assertTrue(run.call_args.kwargs['preview'])
            self.assertEqual(run.call_args.kwargs['captured_images'],['image'])

    def test_reference_capture_needs_no_regions_and_keeps_both_images(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            images=[Image.new('RGB',(40,40),'white'),Image.new('RGB',(40,40),'black')]
            with patch('action.capture',return_value=images) as acquire,patch('action.run') as recognize:
                result=action.execute({},self.settings,context={'mode':'reference_capture','output_dir':folder})
            self.assertEqual(result['status'],'read');acquire.assert_called_once();recognize.assert_not_called()
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['reference-1.png','reference-2.png'])

    def test_discard_first_keeps_requested_images_and_waits(self):
        for count in (1,2):
            with self.subTest(count=count):
                self.ha.reset_mock();self.ha.capture.side_effect=[b'dark',b'one',b'two']
                config={**self.settings['capture'],'count':count,'discard_first':True}
                with patch('capture.decode',side_effect=lambda x:x) as decode,patch('capture.time.sleep') as sleep:
                    self.assertEqual(capture({'capture':config},self.context),[b'one',b'two'][:count])
                self.assertEqual(self.ha.capture.call_count,count+1)
                self.assertEqual([c.args for c in decode.call_args_list],[(b'one',),(b'two',)][:count])
                self.assertEqual([c.args for c in sleep.call_args_list],[(2,)]+[(1,)]*count)
                self.ha.restore.assert_called_once_with('light.meter')
