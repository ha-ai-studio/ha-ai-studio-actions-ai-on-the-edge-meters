import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'actions/analog-meter-reading'))
from correction import combine,analog,hybrid


class CorrectionTests(unittest.TestCase):
    def test_upstream_postprocessing_vectors(self):
        # Adapted upstream test_flowpostprocessing.cpp vectors; see THIRD_PARTY.md.
        cases=[([1.2,6.7],[9.5,8.4],'16.98'),([3.,7.,6.,5.,2.5,9.6],[6.4],'376529.6'),
               ([1.1,6.,7.,7.,3.,4.6],[6.2],'167734.6'),([5.,8.6],[9.8,6.7,8.9,8.6,9.8],'58.96889'),
               ([2.9,7.,6.8,9.9,8.,3.9],[9.7],'377083.9'),([1.1,9.,4.],[6.1,2.6,6.25,9.7],'194.6259')]
        for digits,pointers,expected in cases:
            with self.subTest(expected=expected):self.assertEqual(combine(digits,pointers),expected)
    def test_precision_zero_and_rejection(self):
        self.assertEqual(combine([1.2,6.7],[9.5,8.4],extended=True),'16.984')
        self.assertEqual(combine([0.0],[],shift=-3),'0.000')
        self.assertEqual(combine([1.995],[],extended=True),'1.9')
        self.assertEqual(combine([9.999],[],extended=True),'9.9')
        self.assertEqual(combine([1.1,1.995],[],extended=True),'11.9')
        with self.assertRaises(ValueError):combine([float('nan')],[])
        with self.assertRaises(ValueError):combine([],[])


try:
    from PIL import Image, ImageDraw
    import numpy as np
    from engine import align,box,decode,run,source,ReadingError,Models,crop_inputs,rotated,resolve_layouts
    HAS_RUNTIME=True
except ImportError:
    HAS_RUNTIME=False


@unittest.skipUnless(HAS_RUNTIME,'Run engine tests with the locked Linux Action environment.')
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.assets=self.root/'assets';self.assets.mkdir();self.output=self.root/'output';self.output.mkdir()
        self.context={'assets_dir':str(self.assets),'output_dir':str(self.output),'mode':'preview'}
        self.image=Image.new('RGB',(640,480),'#e7ecef');draw=ImageDraw.Draw(self.image)
        draw.rectangle((30,30,75,75),fill='black');draw.line((30,30,75,75),fill='white',width=8)
        draw.ellipse((540,350,590,400),fill='black');draw.line((540,375,590,375),fill='white',width=8)
        draw.rectangle((160,100,210,180),fill='white');draw.text((175,130),'7',fill='black',font_size=40)
        draw.ellipse((280,100,370,190),fill='white',outline='black',width=3);draw.line((325,145,350,120),fill='red',width=4)
        self.ident=self.save_image(self.image)
        self.settings={'reference':{'asset_id':self.ident,'width':640,'height':480},'regions':[
          {'id':'ref-a','name':'A','kind':'alignment','x':25,'y':25,'width':60,'height':60,'order':0},
          {'id':'ref-b','name':'B','kind':'alignment','x':535,'y':345,'width':65,'height':65,'order':0},
          {'id':'digit-a','name':'Digit','kind':'digit','x':160,'y':100,'width':50,'height':80,'order':0,'meter':'main'},
          {'id':'dial-a','name':'Dial','kind':'analog','x':280,'y':100,'width':90,'height':90,'order':0,'meter':'main'}],
          'meters':[{'id':'main','name':'Synthetic meter','unit':'m3'}]}
        self.data={'image':{'asset_id':self.ident}}
    def save_image(self,image):
        from io import BytesIO
        stream=BytesIO();image.save(stream,format='PNG');data=stream.getvalue();ident=hashlib.sha256(data).hexdigest()+'.png';(self.assets/ident).write_bytes(data);return ident
    def test_alignment_translation_and_bad_references(self):
        from PIL import ImageChops
        shifted=ImageChops.offset(self.image,5,8)
        result,diagnostic=align(shifted,self.image,self.settings['regions'][:2],20,.7)
        self.assertAlmostEqual(diagnostic['translation'][0],-5,places=2);self.assertAlmostEqual(diagnostic['translation'][1],-8,places=2)
        self.assertLess(float(np.abs(np.asarray(result,dtype=float)[30:400,30:600]-np.asarray(self.image,dtype=float)[30:400,30:600]).mean()),1)
        with self.assertRaises(ReadingError):align(self.image.resize((320,240)),self.image,self.settings['regions'][:2],20,.7)
        with self.assertRaises(ReadingError):align(self.image,self.image,[],20,.7)
    def test_preview_model_pipeline_and_no_network(self):
        original=copy.deepcopy((self.data,self.settings))
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No preview downloads')):
            result=run(self.data,self.settings,self.context,preview=True)
        self.assertEqual(len(result['regions']),2)
        self.assertTrue(all(math.isfinite(r['raw']) for r in result['regions']))
        self.assertEqual(result['alignment']['scores'],[1.,1.])
        self.assertTrue((self.output/'aligned.jpg').is_file())
        self.assertEqual((self.data,self.settings),original)
        with self.assertRaises(ReadingError):source({'image':{'url':'https://example.invalid/image'}},{'image_url':'https://example.invalid/image'},self.context)
    def test_request_url_needs_no_configured_source(self):
        from io import BytesIO
        image_bytes=BytesIO();self.image.save(image_bytes,format='PNG')
        for settings in ({}, {'image_url':'https://old.invalid/image'}):
            with patch('urllib.request.OpenerDirector.open',return_value=BytesIO(image_bytes.getvalue())) as opened:
                result=source({'image':{'url':'https://example.invalid/current.png'}},settings,{'mode':'execute'})
                self.assertEqual(result.size,self.image.size)
                self.assertEqual(opened.call_args.args[0],'https://example.invalid/current.png')
        for url in ('file:///tmp/image.png','https://user:password@example.invalid/image','https://example.invalid/image#fragment'):
            with patch('urllib.request.OpenerDirector.open') as opened:
                with self.assertRaises(ReadingError):source({'image':{'url':url}},{},{'mode':'execute'})
                opened.assert_not_called()

    def test_plausibility_and_rejected_roi_do_not_invent_value(self):
        with patch.object(Models,'read',side_effect=[(7.,1.,True),(5.,1.,True)]):
            result=run(self.data,self.settings,self.context)
        self.assertEqual(result['readings'][0]['value'],7.5)
        data={**self.data,'previous':{'main':{'value':8.}}}
        with patch.object(Models,'read',side_effect=[(7.,1.,True),(5.,1.,True)]):
            result=run(data,self.settings,self.context)
        self.assertIsNone(result['readings'][0]['value']);self.assertEqual(result['status'],'unreadable')
        with patch.object(Models,'read',return_value=(1.,.1,False)):
            result=run(self.data,self.settings,self.context)
        self.assertIsNone(result['readings'][0]['value'])
    def test_crop_preserves_regions_and_applies_to_preview(self):
        settings=copy.deepcopy(self.settings)
        settings['crop']={'x':15,'y':15,'width':600,'height':410}
        original=copy.deepcopy(settings)
        result=run(self.data,settings,self.context,preview=True)
        self.assertEqual(len(result['regions']),2)
        with Image.open(self.output/'aligned.jpg') as output:self.assertEqual(output.size,(600,410))
        self.assertEqual(settings,original)
        image,reference,rois=crop_inputs(self.image,self.image,settings['regions'],settings['crop'])
        self.assertEqual(rois[2]['x'],145)
        self.assertEqual(rois[2]['y'],85)
        self.assertEqual(image.crop(box(rois[2],image.size)).tobytes(),self.image.crop(box(settings['regions'][2],self.image.size)).tobytes())
        settings['crop']['x']=40
        with self.assertRaisesRegex(ReadingError,'include all'):run(self.data,settings,self.context)
        with self.assertRaises(ReadingError):crop_inputs(self.image.resize((320,240)),self.image,[],original['crop'])
        with self.assertRaises(ReadingError):crop_inputs(self.image,self.image,[],{'x':0,'y':0,'width':641,'height':480})

    def test_alignment_rejects_missing_pixels_at_crop_edge(self):
        from PIL import ImageChops
        for dx,dy,x,y in [(-8,0,0,100),(8,0,590,100),(0,-8,160,0),(0,8,160,400)]:
            with self.subTest(dx=dx,dy=dy):
                shifted=ImageChops.offset(self.image,dx,dy)
                reading={'x':x,'y':y,'width':50,'height':80}
                with self.assertRaisesRegex(ReadingError,'beyond the available image'):
                    align(shifted,self.image,self.settings['regions'][:2],20,.7,[reading])

    def test_crop_after_rotation(self):
        crop={'x':15,'y':15,'width':600,'height':410}
        rois=copy.deepcopy(self.settings['regions'])
        for region in [crop,*rois]:
            x,y,w,h=(region[k] for k in ('x','y','width','height'))
            region.update(x=480-y-h,y=x,width=h,height=w)
        image=rotated(self.image,90)
        cropped,_,translated=crop_inputs(image,image,rois,crop)
        self.assertEqual(cropped.size,(410,600))
        self.assertEqual(cropped.crop(box(translated[2],cropped.size)).tobytes(),image.crop(box(rois[2],image.size)).tobytes())

    def test_unassigned_frame_is_rejected_before_inference(self):
        settings=copy.deepcopy(self.settings)
        settings['regions'][2]['kind']='unassigned'
        with patch.object(Models,'read',side_effect=AssertionError('No inference before assigning frame types')):
            with self.assertRaisesRegex(ReadingError,'Choose a type'):
                run(self.data,settings,self.context)

    def test_value_pills_decimal_placement_and_legacy_preservation(self):
        original=copy.deepcopy(self.settings)
        self.assertEqual(resolve_layouts(self.settings),original)
        for layout,expected in [(['digit-a',',','dial-a'],7.5),(['digit-a','dial-a'],75.),([',','digit-a','dial-a'],.75)]:
            with self.subTest(layout=layout):
                settings=copy.deepcopy(self.settings);settings['meters'][0]['layout']=layout
                before=copy.deepcopy(settings)
                with patch.object(Models,'read',side_effect=[(7.,1.,True),(5.,1.,True)]):
                    result=run(self.data,settings,self.context)
                self.assertEqual(result['readings'][0]['value'],expected)
                self.assertEqual(settings,before)

    def test_explicit_mapping_ignores_saved_extended_resolution(self):
        for layout,expected in [(['digit-a',',','dial-a'],7.5),(['digit-a','dial-a'],75.)]:
            settings=copy.deepcopy(self.settings)
            settings['meters'][0].update(layout=layout,extended_resolution=True)
            before=copy.deepcopy(settings)
            with patch.object(Models,'read',side_effect=[(7.,1.,True),(5.8,1.,True)]):
                result=run(self.data,settings,self.context)
            self.assertEqual(result['readings'][0]['value'],expected)
            self.assertEqual(settings,before)

    def test_value_pills_reject_invalid_frames_and_ignore_unused(self):
        for layout in [[],[','],['missing'],['ref-a'],['digit-a','digit-a'],['digit-a',',',','],['dial-a','digit-a']]:
            with self.subTest(layout=layout):
                settings=copy.deepcopy(self.settings);settings['meters'][0]['layout']=layout
                with self.assertRaises(ReadingError):resolve_layouts(settings)
        settings=copy.deepcopy(self.settings);settings['meters'][0]['layout']=['digit-a']
        settings['regions'].append({**settings['regions'][2],'id':'unused','kind':'unassigned'})
        self.assertEqual([r['id'] for r in resolve_layouts(settings)['regions']],['ref-a','ref-b','digit-a'])
        settings['meters'].append({'id':'second','layout':['digit-a']})
        with self.assertRaises(ReadingError):resolve_layouts(settings)

    def test_invalid_geometry_and_decode(self):
        with self.assertRaises(ReadingError):box({'x':600,'y':0,'width':80,'height':20},(640,480))
        with self.assertRaises(ReadingError):decode(b'<svg>not an image</svg>')
        changed=copy.deepcopy(self.settings);changed['regions'][2]['meter']='missing'
        with self.assertRaises(ReadingError):run(self.data,changed,self.context)
        changed=copy.deepcopy(self.settings);changed['regions'][2]['order']=0;changed['regions'].append({**changed['regions'][2],'id':'duplicate-position'})
        with patch.object(Models,'read',return_value=(1.,1.,True)):
            result=run(self.data,changed,self.context)
        self.assertIsNone(result['readings'][0]['value'])

if __name__=='__main__':unittest.main()
