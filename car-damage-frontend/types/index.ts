// ── Enums ─────────────────────────────────────────────────────────────────────

export type DamageClass = 'scratch' | 'dent' | 'paint_damage' | 'crack';
export type CameraAngle =
  | 'front'
  | 'rear'
  | 'left'
  | 'right'
  | 'front_oblique'
  | 'rear_oblique';
export type ScanStatus = 'pending' | 'processing' | 'complete' | 'failed';

// ── API envelope ──────────────────────────────────────────────────────────────

export interface APIResponse<T> {
  success: boolean;
  data: T;
  error: string | null;
  meta: Record<string, unknown>;
}

export interface PaginatedMeta {
  page: number;
  limit: number;
  total: number;
}

// ── Domain models ─────────────────────────────────────────────────────────────

export interface Vehicle {
  id: string;
  plate_number: string;
  first_seen: string;
  last_seen: string;
  total_scans: number;
}

export interface Scan {
  id: string;
  vehicle_id: string;
  triggered_at: string;
  completed_at: string | null;
  camera_count: number;
  status: ScanStatus;
  location_tag: string | null;
}

export interface ScanImage {
  id: string;
  scan_id: string;
  camera_angle: CameraAngle;
  full_image_path: string;
  thumbnail_path: string;
  captured_at: string;
}

export interface DamageRecord {
  id: string;
  scan_id: string;
  scan_image_id: string;
  damage_class: DamageClass;
  confidence: number;
  bbox_x1: number;
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
  polygon_points: [number, number][];
  mask_area_px: number;
  mask_area_pct: number;
  crop_image_path: string;
  is_new_damage: boolean | null;
}

export interface ScanDetail extends Scan {
  images: ScanImage[];
  damage_records: DamageRecord[];
}

export interface DamageDiff {
  id: string;
  vehicle_id: string;
  scan_id_old: string | null;
  scan_id_new: string;
  new_damage_count: number;
  resolved_damage_count: number;
  diff_summary: {
    total_new: number;
    total_resolved: number;
    total_existing: number;
    new_damage_details: unknown[];
    prior_scan_id: string | null;
  };
  computed_at: string;
}

export interface AlertLog {
  id: string;
  scan_id: string;
  vehicle_id: string;
  webhook_id: string;
  status_code: number;
  triggered_at: string;
  payload_summary: {
    event: string;
    new_damage_count: number;
    plate_number: string;
  };
}

// ── Canvas / overlay ──────────────────────────────────────────────────────────

export interface DamageAnnotation {
  id: string;
  className: DamageClass;
  confidence: number;
  bbox: readonly [number, number, number, number]; // [x1, y1, x2, y2]
  polygon: ReadonlyArray<readonly [number, number]>;
  isNew?: boolean | null;
  /** 0 = likely real damage, 1 = likely light reflection / glare */
  reflectionScore?: number;
}

export function recordToAnnotation(r: DamageRecord): DamageAnnotation {
  return {
    id: r.id,
    className: r.damage_class,
    confidence: r.confidence,
    bbox: [r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2],
    polygon: r.polygon_points,
    isNew: r.is_new_damage,
  };
}

// ── WebSocket messages ────────────────────────────────────────────────────────

export interface WSDamage {
  annotation_id: string;
  class_name: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
  mask_area_pct: number;
}

export interface WSPlate {
  plate_text: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface WSInspectionFrame {
  event: 'inspection_result';
  camera_id: string;
  angle: CameraAngle;
  captured_at: string;
  frame_hash: string;
  plate: WSPlate | null;
  damages: WSDamage[];
  n_damages: number;
}

export interface WSConnected {
  event: 'connected';
  timestamp: string;
  mode: string;
}

export type WSMessage = WSInspectionFrame | WSConnected | { event: 'ping' };

export function wsDamageToAnnotation(d: WSDamage): DamageAnnotation {
  return {
    id: d.annotation_id,
    className: d.class_name as DamageClass,
    confidence: d.confidence,
    bbox: d.bbox_xyxy,
    polygon: [],
    isNew: undefined,
  };
}
