import type { Crop } from './types';
export type CropHandle = 'nw'|'n'|'ne'|'e'|'se'|'s'|'sw'|'w'|'move';
export const cropHandles = (r:Crop) => [
  ['nw',r.x,r.y],['n',r.x+r.width/2,r.y],['ne',r.x+r.width,r.y],
  ['e',r.x+r.width,r.y+r.height/2],['se',r.x+r.width,r.y+r.height],
  ['s',r.x+r.width/2,r.y+r.height],['sw',r.x,r.y+r.height],['w',r.x,r.y+r.height/2],
] as [CropHandle,number,number][];
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));
export function hitCrop(r:Crop,x:number,y:number,tolerance:number):CropHandle|null {
  for(const [handle,hx,hy] of cropHandles(r))if(Math.abs(x-hx)<=tolerance&&Math.abs(y-hy)<=tolerance)return handle;
  return x>=r.x&&x<=r.x+r.width&&y>=r.y&&y<=r.y+r.height?'move':null;
}
export function adjustCrop(r:Crop,handle:CropHandle,dx:number,dy:number,width:number,height:number):Crop {
  dx=Math.round(dx);dy=Math.round(dy);
  if(handle==='move')return {...r,x:clamp(r.x+dx,0,width-r.width),y:clamp(r.y+dy,0,height-r.height)};
  let left=r.x,top=r.y,right=r.x+r.width,bottom=r.y+r.height;
  if(handle.includes('w'))left=clamp(left+dx,0,right-4);
  if(handle.includes('e'))right=clamp(right+dx,left+4,width);
  if(handle.includes('n'))top=clamp(top+dy,0,bottom-4);
  if(handle.includes('s'))bottom=clamp(bottom+dy,top+4,height);
  return {x:left,y:top,width:right-left,height:bottom-top};
}
