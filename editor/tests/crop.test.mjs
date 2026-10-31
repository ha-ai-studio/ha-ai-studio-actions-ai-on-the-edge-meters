import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cropHandles,hitCrop,adjustCrop} from '../src/crop.ts';
const r={x:20,y:30,width:200,height:100};
test('all eight grips are selectable, including just outside the frame',()=>{
  for(const [handle,x,y] of cropHandles(r))assert.equal(hitCrop(r,x,y,10),handle);
  assert.equal(hitCrop(r,15,25,10),'nw');
  assert.equal(hitCrop(r,100,80,10),'move');
  assert.equal(hitCrop(r,0,0,10),null);
});
test('opposite edges stay fixed and grips cannot cross',()=>{
  assert.deepEqual(adjustCrop(r,'nw',30,20,640,480),{x:50,y:50,width:170,height:80});
  assert.deepEqual(adjustCrop(r,'e',-999,0,640,480),{...r,width:4});
  assert.deepEqual(adjustCrop(r,'sw',999,-999,640,480),{x:216,y:30,width:4,height:4});
  for(const [handle] of cropHandles(r))for(const delta of [-1000,1000]){
    const next=adjustCrop(r,handle,delta,delta,640,480);
    assert.ok(next.x>=0&&next.y>=0&&next.width>=4&&next.height>=4);
    assert.ok(next.x+next.width<=640&&next.y+next.height<=480);
  }
});
test('moving keeps dimensions and clamps to image bounds without mutating the start',()=>{
  assert.deepEqual(adjustCrop(r,'move',999,999,640,480),{x:440,y:380,width:200,height:100});
  assert.deepEqual(adjustCrop(r,'move',-999,-999,640,480),{x:0,y:0,width:200,height:100});
  assert.deepEqual(r,{x:20,y:30,width:200,height:100});
});
