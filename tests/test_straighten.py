import copy
import math
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
import test_analog_meter_reading as fixtures
from engine import straighten,run,ReadingError,Models,align,rotated

class StraightenTests(unittest.TestCase):
    def test_alignment_rejects_padded_matched_anchor(self):
        f=fixtures.EngineTests();f.setUp();self.addCleanup(f.doCleanups)
        validity=np.ones((480,640),dtype=np.float32);validity[25,25]=0
        with self.assertRaisesRegex(ReadingError,'Matched alignment reference'):
            align(f.image,f.image,f.settings['regions'][:2],0,.7,[],validity)

    def test_quarter_turn_straightening_and_crop(self):
        f=fixtures.EngineTests();f.setUp();self.addCleanup(f.doCleanups)
        settings=copy.deepcopy(f.settings);settings.update(rotation=90,straighten_angle=2,crop=dict(x=5,y=5,width=470,height=630))
        angle=math.radians(2);c=math.cos(angle);s=math.sin(angle)
        for r in settings['regions']:
            x,y,w,h=r['x'],r['y'],r['width'],r['height']
            r.update(x=480-y-h,y=x,width=h,height=w)
            points=[(240+c*(x-240)-s*(y-320),320+s*(x-240)+c*(y-320)) for x,y in [(r['x'],r['y']),(r['x']+r['width'],r['y']),(r['x'],r['y']+r['height']),(r['x']+r['width'],r['y']+r['height'])]]
            x=math.floor(min(p[0] for p in points));y=math.floor(min(p[1] for p in points))
            r.update(x=x,y=y,width=math.ceil(max(p[0] for p in points))-x,height=math.ceil(max(p[1] for p in points))-y)
        with patch.object(Models,'read',side_effect=[(7.,1,True),(5.,1,True)]):
            result=run(f.data,settings,f.context,preview=True)
        self.assertEqual(result['status'],'read')
        expected,_=straighten(rotated(f.image,90),2);expected=expected.crop((5,5,475,635))
        with Image.open(f.output/'aligned.jpg') as aligned:
            self.assertEqual(aligned.size,(470,630))
            self.assertLess(np.abs(np.asarray(aligned,dtype=float)-np.asarray(expected,dtype=float)).mean(),3)

    def test_clockwise_canvas_convention_and_horizontal_line(self):
        image=Image.new('RGB',(640,480),'white')
        ImageDraw.Draw(image).line((200,220,400,260),fill='black',width=3)
        result,mask=straighten(image,-math.degrees(math.atan2(40,200)))
        pixels=np.asarray(result)
        for x in (230,370):
            dark=np.where(pixels[225:255,x,0]<100)[0]+225
            expected_y=239.5+math.sin(-math.atan2(40,200))*(300-319.5)+math.cos(-math.atan2(40,200))*(240-239.5)
            self.assertTrue(len(dark)>0);self.assertLessEqual(abs(float(dark.mean())-expected_y),1)
        self.assertEqual(result.size,image.size);self.assertLess(mask[0,0],1)
        original,valid=straighten(image,0);self.assertEqual(original.tobytes(),image.tobytes());self.assertTrue(np.all(valid==1))
        with self.assertRaises(ReadingError):straighten(image,float('nan'))

    def test_rotated_reference_and_request_share_geometry(self):
        f=fixtures.EngineTests();f.setUp();self.addCleanup(f.doCleanups)
        settings=copy.deepcopy(f.settings);settings['straighten_angle']=2
        angle=math.radians(2);c=math.cos(angle);s=math.sin(angle)
        for r in settings['regions']:
            points=[(320+c*(x-320)-s*(y-240),240+s*(x-320)+c*(y-240)) for x,y in [(r['x'],r['y']),(r['x']+r['width'],r['y']),(r['x'],r['y']+r['height']),(r['x']+r['width'],r['y']+r['height'])]]
            x=math.floor(min(p[0] for p in points));y=math.floor(min(p[1] for p in points))
            r.update(x=x,y=y,width=math.ceil(max(p[0] for p in points))-x,height=math.ceil(max(p[1] for p in points))-y)
        original=copy.deepcopy(settings)
        with patch.object(Models,'read',side_effect=[(7.,1,True),(5.,1,True)]):
            result=run(f.data,settings,f.context,preview=True)
        self.assertEqual(result['readings'][0]['value'],7.5);self.assertEqual(settings,original)
        expected,_=straighten(f.image,2)
        with Image.open(f.output/'aligned.jpg') as aligned:
            self.assertLess(np.abs(np.asarray(aligned,dtype=float)-np.asarray(expected,dtype=float)).mean(),3)
        settings['regions'][2].update(x=0,y=0,width=20,height=20)
        with patch.object(Models,'read',side_effect=AssertionError('No inference on empty corners')):
            with self.assertRaisesRegex(ReadingError,'empty corner'):run(f.data,settings,f.context)

if __name__=='__main__':unittest.main()
