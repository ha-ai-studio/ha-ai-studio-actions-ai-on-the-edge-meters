import {test} from 'node:test';
import assert from 'node:assert/strict';
import {lineCorrection,rotateBounds,rotatePoint} from '../src/straighten.ts';
test('line becomes horizontal regardless of drawing direction',()=>{
  for(const [a,b] of [[{x:10,y:20},{x:210,y:60}],[{x:210,y:60},{x:10,y:20}],[{x:10,y:60},{x:210,y:20}],[{x:10,y:20},{x:10,y:120}]]){
    const radians=lineCorrection(a,b)*Math.PI/180;
    assert.ok(Math.abs(Math.sin(radians)*(b.x-a.x)+Math.cos(radians)*(b.y-a.y))<1e-8);
    assert.ok(Math.abs(lineCorrection(a,b))<=90);
  }
});
test('region bounds preserve a zero rotation and enclose all rotated corners',()=>{
  const r={x:180,y:100,width:70,height:90};assert.deepEqual(rotateBounds(r,640,480,0),r);
  for(const angle of [-40,-2,2,40,90]){
    const b=rotateBounds(r,640,480,angle),c=Math.cos(angle*Math.PI/180),s=Math.sin(angle*Math.PI/180);
    for(const [x,y]of [[180,100],[250,100],[180,190],[250,190]]){
      const px=320+c*(x-320)-s*(y-240),py=240+s*(x-320)+c*(y-240);
      assert.ok(px>=b.x-1e-8&&px<=b.x+b.width+1e-8&&py>=b.y-1e-8&&py<=b.y+b.height+1e-8);
    }
  }
});

test('saved guide follows image rotation and becomes horizontal',()=>{
  const a={x:130,y:170},b={x:420,y:220},angle=lineCorrection(a,b);
  const start=rotatePoint(a,640,480,angle),end=rotatePoint(b,640,480,angle);
  assert.ok(Math.abs(start.y-end.y)<1e-8);
  assert.ok(Math.abs(Math.hypot(end.x-start.x,end.y-start.y)-Math.hypot(b.x-a.x,b.y-a.y))<1e-8);
});
