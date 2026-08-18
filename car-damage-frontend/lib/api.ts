import type {
  Vehicle,
  Scan,
  ScanDetail,
  DamageRecord,
  DamageDiff,
  AlertLog,
  APIResponse,
} from '@/types';

// ── Base URLs ─────────────────────────────────────────────────────────────────
// All requests go through Next.js rewrites → no CORS issues in the browser.
// SSR uses direct backend URL via BACKEND_URL env var.

export const API_BASE =
  typeof window !== 'undefined'
    ? '/api/v1'
    : (process.env.BACKEND_URL ?? 'http://localhost:8000') + '/api/v1';

// Inference service — proxied through /api/inference → localhost:8001
export const INFERENCE_BASE =
  typeof window !== 'undefined'
    ? '/api/inference'
    : (process.env.INFERENCE_URL ?? 'http://localhost:8001');

// WebSocket can't be proxied by Next.js — direct connection, CORS now whitelisted
export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8001/ws/live-feed';

export const MINIO_URL =
  process.env.NEXT_PUBLIC_MINIO_URL ?? 'http://localhost:9000';

export const BUCKET = {
  FULL:   'car-damage-full-images',
  CROPS:  'car-damage-crops',
  THUMBS: 'car-damage-thumbnails',
} as const;

export function minioUrl(bucket: string, path: string): string {
  return `${MINIO_URL}/${bucket}/${path}`;
}

// ── SWR fetcher ───────────────────────────────────────────────────────────────

export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const json = (await res.json()) as APIResponse<unknown>;
      msg = json.error ?? msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  const json = (await res.json()) as APIResponse<T>;
  if (!json.success) throw new Error(json.error ?? 'API error');
  return json.data;
}

// ── URL builders ──────────────────────────────────────────────────────────────

export function vehiclesUrl(params?: {
  plate?: string;
  page?: number;
  limit?: number;
}): string {
  const q = new URLSearchParams();
  if (params?.plate) q.set('plate', params.plate);
  if (params?.page  != null) q.set('page',  String(params.page));
  if (params?.limit != null) q.set('limit', String(params.limit));
  const qs = q.toString();
  return `${API_BASE}/vehicles${qs ? '?' + qs : ''}`;
}

export const urls = {
  vehicles:        (p?: { plate?: string; page?: number; limit?: number }) => vehiclesUrl(p),
  vehicle:         (id: string) => `${API_BASE}/vehicles/${id}`,
  vehicleScans:    (id: string, limit = 20) => `${API_BASE}/vehicles/${id}/scans?limit=${limit}`,
  vehicleLatest:   (id: string) => `${API_BASE}/vehicles/${id}/scans/latest`,
  scan:            (id: string) => `${API_BASE}/scans/${id}`,
  scanDamages:     (id: string) => `${API_BASE}/scans/${id}/damages`,
  scanDiff:        (id: string) => `${API_BASE}/scans/${id}/diff`,
  scanReport:      (id: string) => `${API_BASE}/scans/${id}/report`,
  alerts:          (limit = 50) => `${API_BASE}/alerts/recent?limit=${limit}`,
  // Inference
  inspectFrame:    () => `${INFERENCE_BASE}/api/v1/inspect/frame`,
  inspectBatch:    () => `${INFERENCE_BASE}/api/v1/inspect/batch`,
  inspectTest:     () => `${INFERENCE_BASE}/api/v1/inspect/test`,
  modelStatus:     () => `${INFERENCE_BASE}/api/v1/model/status`,
};

// ── Typed helpers ─────────────────────────────────────────────────────────────

export async function fetchVehicle(id: string): Promise<Vehicle> {
  return fetcher<Vehicle>(urls.vehicle(id));
}
export async function fetchScan(id: string): Promise<ScanDetail> {
  return fetcher<ScanDetail>(urls.scan(id));
}
export async function fetchScanDamages(id: string): Promise<DamageRecord[]> {
  return fetcher<DamageRecord[]>(urls.scanDamages(id));
}
export async function fetchScanDiff(id: string): Promise<DamageDiff> {
  return fetcher<DamageDiff>(urls.scanDiff(id));
}
export async function fetchAlerts(limit = 50): Promise<AlertLog[]> {
  return fetcher<AlertLog[]>(urls.alerts(limit));
}
export async function fetchVehicleScans(vehicleId: string): Promise<Scan[]> {
  return fetcher<Scan[]>(urls.vehicleScans(vehicleId));
}

// ── Inference helpers ─────────────────────────────────────────────────────────

export interface InspectResult {
  camera_id: string;
  vehicle_id: string;
  plate_result: { plate_text: string; confidence: number; bbox: number[] } | null;
  damages: Array<{
    annotation_id: string;
    class_name: string;
    confidence: number;
    bbox_xyxy: [number, number, number, number];
    polygon_points: [number, number][];
    mask_area_px: number;
    mask_area_pct: number;
    crop_b64: string;
    reflection_score: number;
  }>;
  inference_time_ms: number;
  captured_at: string;
}

export async function inspectImageFile(
  file: File,
  cameraId = 'upload',
  vehicleId = '',
): Promise<InspectResult> {
  const form = new FormData();
  form.append('image',      file);
  form.append('camera_id',  cameraId);
  form.append('vehicle_id', vehicleId);
  const res = await fetch(urls.inspectFrame(), { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Inference failed: ${res.status} ${res.statusText}`);
  return res.json() as Promise<InspectResult>;
}

export async function runTestInspection(): Promise<InspectResult> {
  const res = await fetch(urls.inspectTest());
  if (!res.ok) throw new Error(`Test inspection failed: ${res.status}`);
  return res.json() as Promise<InspectResult>;
}

/** Submit an InspectResult to the backend and create a Scan record. */
export async function saveScanToBackend(
  plateNumber: string,
  angle: string,
  inspectResult: InspectResult,
  imageFile: File,
  locationTag?: string,
): Promise<ScanDetail> {
  const meta = {
    plate_number: plateNumber.toUpperCase().trim(),
    location_tag: locationTag ?? null,
    inspection_results: [{
      camera_id:        inspectResult.camera_id,
      angle,
      damages:          inspectResult.damages,
      plate_result:     inspectResult.plate_result,
      inference_time_ms: inspectResult.inference_time_ms,
      captured_at:      inspectResult.captured_at,
    }],
  };

  const form = new FormData();
  form.append('metadata', JSON.stringify(meta));
  form.append('images',   imageFile, `${inspectResult.camera_id}.jpg`);

  const res = await fetch(`${API_BASE}/scans`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Save failed: ${res.status} ${res.statusText}`);
  const body = (await res.json()) as APIResponse<ScanDetail>;
  if (!body.success) throw new Error(body.error ?? 'Save failed');
  return body.data;
}
