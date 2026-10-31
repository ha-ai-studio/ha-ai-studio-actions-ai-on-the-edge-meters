import type { Crop } from './types';
export function lineCorrection(a:{x:number;y:number},b:{x:number;y:number}):number {
  let angle=Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI;
  if(angle>90)angle-=180;if(angle< -90)angle+=180;
  return -angle;
}
export function rotateBounds(r:Crop,width:number,height:number,degrees:number):Crop {
  const angle=degrees*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
  const points=[[r.x,r.y],[r.x+r.width,r.y],[r.x,r.y+r.height],[r.x+r.width,r.y+r.height]].map(([x,y])=>({x:width/2+c*(x-width/2)-s*(y-height/2),y:height/2+s*(x-width/2)+c*(y-height/2)}));
  const x=Math.floor(Math.min(...points.map(p=>p.x))+1e-8),y=Math.floor(Math.min(...points.map(p=>p.y))+1e-8);
  return {x,y,width:Math.ceil(Math.max(...points.map(p=>p.x))-1e-8)-x,height:Math.ceil(Math.max(...points.map(p=>p.y))-1e-8)-y};
}

export function rotatePoint(p:{x:number;y:number},width:number,height:number,degrees:number):{x:number;y:number} {
  const angle=degrees*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
  return {x:width/2+c*(p.x-width/2)-s*(p.y-height/2),y:height/2+s*(p.x-width/2)+c*(p.y-height/2)};
}
