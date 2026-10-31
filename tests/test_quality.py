import copy
import unittest
from unittest.mock import patch
import test_analog_meter_reading as fixtures
from engine import run, read_model_region, Models, ReadingError, prepare_crop
from PIL import Image

class QualityTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.EngineTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.settings=copy.deepcopy(self.f.settings)
        self.roi=self.settings['regions'][2]

    def test_five_positions_thresholds_and_unstable_frame(self):
        self.settings.update(stability_check=True,digit_threshold=.8,analog_threshold=.9)
        with patch.object(Models,'read',return_value=(7.1,.9,True)) as model:
            result=read_model_region(self.f.image,self.roi,self.settings,Models())
        self.assertTrue(result[2]);self.assertEqual(len(result[4]),5)
        self.assertEqual([call.args[-1] for call in model.call_args_list],[.8]*5)
        with patch.object(Models,'read',side_effect=[(7.1,.9,True),(7.6,.9,True)]):
            result=read_model_region(self.f.image,self.roi,self.settings,Models())
        self.assertFalse(result[2]);self.assertIn('Unstable',result[3])
        with patch.object(Models,'read',side_effect=[(7.1,.9,True),(7.1,.7,False)]):
            result=read_model_region(self.f.image,self.roi,self.settings,Models())
        self.assertFalse(result[2]);self.assertIn('shifted',result[3])

    def test_circular_distance_and_legacy_defaults(self):
        with patch.object(Models,'read',return_value=(9.95,1,True)) as model:
            self.assertTrue(read_model_region(self.f.image,self.roi,{},Models())[2]);self.assertEqual(model.call_count,1)
        with patch.object(Models,'read',side_effect=[(9.95,1,True)]+[(.05,1,True)]*4):
            self.assertTrue(read_model_region(self.f.image,self.roi,{'stability_check':True},Models())[2])

    def test_preparation_and_margin(self):
        image=Image.new('RGB',(10,10),(120,20,50));image.putpixel((0,0),(180,60,80))
        self.assertEqual(prepare_crop(image,'none').tobytes(),image.tobytes())
        prepared=prepare_crop(image,'grayscale_autocontrast')
        self.assertEqual(prepared.mode,'RGB');self.assertEqual(prepared.getpixel((0,0)),(255,255,255))
        with self.assertRaises(ReadingError):prepare_crop(image,'unknown')
        self.settings['stability_check']=True
        self.settings['regions'][2]['x']=0
        with self.assertRaisesRegex(ReadingError,'two-pixel'):run(self.f.data,self.settings,self.f.context)

    def test_corrected_value_must_agree_and_diagnostics_mark_frame(self):
        self.settings['stability_check']=True
        # Stable raw distance, but a different corrected last dial digit.
        with patch.object(Models,'read',side_effect=[(7.,1,True)]*5+[(5.01,1,True),(4.99,1,True)]+[(5.01,1,True)]*3):
            result=run(self.f.data,self.settings,self.f.context)
        self.assertEqual(result['status'],'unreadable');self.assertIn('stability',result['readings'][0]['reason'])
        self.assertFalse(result['regions'][1]['accepted'])

    def test_confirmation_requires_distinct_images_and_does_not_certify_preview(self):
        self.settings['require_confirmation']=True
        with self.assertRaisesRegex(ReadingError,'second capture'):run(self.f.data,self.settings,self.f.context)
        with patch.object(Models,'read',return_value=(7.,1,True)):
            result=run(self.f.data,self.settings,self.f.context,preview=True)
        self.assertEqual(result['status'],'unreadable');self.assertIsNone(result['readings'][0]['value'])
        self.assertEqual(result['readings'][0]['confirmation'],'not_tested')
        with self.assertRaisesRegex(ReadingError,'identical'):run({**self.f.data,'confirmation_image':self.f.data['image']},self.settings,self.f.context)

    def test_confirmation_agreement_and_disagreement(self):
        image=self.f.image.copy();image.putpixel((630,470),(0,0,0));ident=self.f.save_image(image)
        data={**self.f.data,'confirmation_image':{'asset_id':ident}}
        for values,expected in [([7.,5.,7.,5.],'read'),([7.,5.,8.,5.],'unreadable')]:
            with patch.object(Models,'read',side_effect=[(v,1,True) for v in values]):result=run(data,self.settings,self.f.context)
            self.assertEqual(result['status'],expected)
            self.assertEqual(result['readings'][0]['confirmation'],'passed' if expected=='read' else 'failed')
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ReadingError,'network access'):run({**self.f.data,'confirmation_image':{'url':'https://example.invalid/x'}},self.settings,self.f.context,preview=True)

    def test_confirmation_preserves_other_values_and_preview_failure_reason(self):
        image=self.f.image.copy();image.putpixel((630,470),(0,0,0));ident=self.f.save_image(image)
        self.settings['regions'].append({**self.roi,'id':'serial','kind':'number_block','meter':'serial'})
        self.settings['meters'].append({'id':'serial','name':'Serial','unit':''})
        with patch.object(Models,'read',side_effect=[(7.,1,True),(5.,1,True)]*2), patch('engine.recognize_number_block',side_effect=['001234',ValueError('OCR rejected')]):
            result=run({**self.f.data,'confirmation_image':{'asset_id':ident}},self.settings,self.f.context)
        self.assertEqual(result['status'],'unreadable');self.assertEqual(result['readings'][0]['value'],7.5)
        self.assertIsNone(result['readings'][1]['value'])
        self.settings['require_confirmation']=True
        with patch.object(Models,'read',return_value=(7.,.1,False)),patch('engine.recognize_number_block',return_value='001234'):
            result=run(self.f.data,self.settings,self.f.context,preview=True)
        self.assertIn('threshold',result['readings'][0]['reason'])

    def test_confirmation_shares_deadline(self):
        image=self.f.image.copy();image.putpixel((630,470),(0,0,0));ident=self.f.save_image(image)
        with patch('engine.time.monotonic',side_effect=[0,1,2,21]),patch.object(Models,'read',return_value=(7.,1,True)):
            with self.assertRaisesRegex(ReadingError,'time budget'):
                run({**self.f.data,'confirmation_image':{'asset_id':ident}},self.settings,self.f.context)

    def test_alignment_padding_cannot_enter_shifted_samples(self):
        from PIL import ImageChops
        self.settings['stability_check']=True
        self.settings['regions'][2]['x']=8
        ident=self.f.save_image(ImageChops.offset(self.f.image,-8,0))
        with patch.object(Models,'read',side_effect=AssertionError('No inference on missing pixels')):
            with self.assertRaisesRegex(ReadingError,'beyond the available image'):
                run({'image':{'asset_id':ident}},self.settings,self.f.context)

    def test_rate_plus_tolerance(self):
        self.settings['meters'][0].update(max_rate=1,rate_tolerance=.2)
        data={**self.f.data,'previous':{'main':{'value':6.35,'elapsed_seconds':60}}}
        with patch.object(Models,'read',side_effect=[(7.,1,True),(5.,1,True)]):result=run(data,self.settings,self.f.context)
        self.assertEqual(result['status'],'read')
        self.settings['meters'][0]['rate_tolerance']=.1
        with patch.object(Models,'read',side_effect=[(7.,1,True),(5.,1,True)]):result=run(data,self.settings,self.f.context)
        self.assertEqual(result['status'],'unreadable')

if __name__=='__main__':unittest.main()
