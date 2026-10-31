import type { Settings, ReferenceImage } from './types';
export function referenceImages(settings:Settings):ReferenceImage[] {
  const images=[...(settings.references??[])];
  if(settings.reference&&!images.some(r=>r.asset_id===settings.reference!.asset_id))images.unshift(settings.reference);
  return images.filter((r,i)=>images.findIndex(other=>other.asset_id===r.asset_id)===i);
}
export function addReference(settings:Settings,image:ReferenceImage):ReferenceImage[] {
  const images=referenceImages(settings);
  if(images.some(r=>r.width!==image.width||r.height!==image.height))throw new Error('Additional reference images must have the same dimensions to preserve frames and crop.');
  if(images.some(r=>r.asset_id===image.asset_id))return images;
  if(images.length>=16)throw new Error('Use at most 16 reference images.');
  return [...images,image];
}
