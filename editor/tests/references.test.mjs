import {test} from 'node:test';
import assert from 'node:assert/strict';
import {referenceImages,addReference} from '../src/references.ts';
const a={asset_id:'a',width:640,height:480},b={asset_id:'b',width:640,height:480};
test('legacy reference joins gallery without duplicating or changing shared geometry',()=>{
 const settings={reference:a,regions:[{id:'frame',x:10}],rotation:90,straighten_angle:2,crop:{x:5,y:5,width:400,height:400}};
 const before=structuredClone(settings);
 assert.deepEqual(referenceImages(settings),[a]);assert.deepEqual(addReference(settings,b),[a,b]);assert.deepEqual(settings,before);
 assert.deepEqual(referenceImages({reference:a,references:[a,b,a]}),[a,b]);
});
test('gallery refuses different sizes and caps images without rejecting duplicate',()=>{
 assert.throws(()=>addReference({reference:a},{...b,width:480,height:640}),/same dimensions/);
 const references=Array.from({length:16},(_,i)=>({...a,asset_id:String(i)}));
 assert.throws(()=>addReference({references},b),/at most 16/);
 assert.deepEqual(addReference({references},references[0]),references);
});
