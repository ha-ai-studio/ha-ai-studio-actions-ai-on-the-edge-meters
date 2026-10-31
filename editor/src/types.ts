export interface Region {
  id:string; name:string; kind:'unassigned'|'alignment'|'digit'|'analog'|'number_block';
  x:number; y:number; width:number; height:number; meter?:string; order:number; ccw?:boolean; expected_length?:number; expected_value?:string;
}
export interface Meter {
  layout?:string[];
  id:string; name:string; unit:string; decimal_shift?:number; extended_resolution?:boolean;
  transition_start?:number; allow_negative?:boolean; max_change?:number; max_rate?:number; rate_tolerance?:number;
}
export interface Crop { x:number; y:number; width:number; height:number; }
export interface ReferenceImage { asset_id:string; width:number; height:number; }
export interface Settings {
  crop?:Crop;
  meter_name?:string; unit?:string; display_type?:string;
  reference?:ReferenceImage; references?:ReferenceImage[];
  rotation?:number; straighten_angle?:number; image_url?:string; search_radius?:number; alignment_threshold?:number;
  stability_check?:boolean; require_confirmation?:boolean; digit_threshold?:number; analog_threshold?:number;
  digit_preprocessing?:'none'|'autocontrast'|'grayscale_autocontrast'; analog_preprocessing?:'none'|'autocontrast'|'grayscale_autocontrast';
  recognition_threshold?:number; regions?:Region[]; meters?:Meter[];
}
export interface Context {
  changed():void;
  uploadImage(file:File):Promise<{id:string;width:number;height:number}>;
  assetUrl(id:string):string;
  removeImage(id:string):Promise<unknown>;
  preview(data:unknown,settings:Settings):Promise<Preview>;
  previewImageUrl(run:string,name:string):string;
}
export interface Preview {
  run:string; images:{name:string}[];
  result:{status:string;message?:string;readings:{id:string;name:string;value:number|string|null;unit:string;reason?:string}[];
    regions:{id:string;raw:number|string|null;fit:number|null;reason?:string|null;accepted:boolean;image:string}[]};
}
