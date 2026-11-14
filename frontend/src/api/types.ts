export interface AOI {
  id: string;
  name: string;
  description: string;
  bbox: [number, number, number, number];
  geometry: GeoJSON.Geometry;
  grid: { crs: string; transform: number[]; width: number; height: number };
  area_km2: number;
  created_at: string;
}

export interface Product {
  id: string;
  aoi_id: string;
  kind: string;
  scene_ids: string[];
  acquired: string;
  acquired_list: string[];
  provider: string;
  collection: string;
  platform: string | null;
  scene_cloud_cover: number | null;
  valid_fraction: number;
  quality_summary: Record<string, number>;
  processing: string[];
  processing_baselines: string[];
  attribution: string | null;
  mgrs_tile: string | null;
  created_at: string;
}

export interface Scene {
  id: string;
  provider: string;
  datetime: string;
  date: string;
  platform: string;
  cloud_cover: number | null;
  mgrs_tile: string | null;
  processing_baseline: string | null;
  thumbnail: string | null;
  bbox: number[];
  properties: Record<string, number>;
}

export interface EpochRow {
  epoch: number;
  train_loss: number;
  val_loss: number | null;
  val_miou: number | null;
  val_accuracy: number | null;
  val_per_class_iou: (number | null)[];
  lr: number;
  seconds: number;
}

export interface Experiment {
  id: string;
  name: string;
  config: Record<string, unknown> & {
    bands: string[];
    train_regions: string[];
    val_regions: string[];
    test_regions: string[];
    epochs: number;
    base: number;
    depth: number;
    batch_size: number;
  };
  status: string;
  job_id: string | null;
  checkpoint: string | null;
  checkpoint_sha256: string | null;
  best_val_miou: number | null;
  best_epoch: number | null;
  n_params: number | null;
  device: string | null;
  result: Record<string, unknown> | null;
  notes: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  calibrated: boolean;
  epochs?: EpochRow[];
}

export interface PerClass {
  class: string;
  iou: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  dice: number | null;
  support: number;
}

export interface SegMetrics {
  overall_accuracy: number | null;
  mean_iou: number | null;
  mean_dice: number | null;
  macro_precision: number | null;
  macro_recall: number | null;
  per_class: PerClass[];
  confusion_matrix: number[][];
  pixels: number;
}

export interface BinaryMetrics {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  iou: number | null;
  accuracy: number;
}

export interface EvaluationResult {
  checkpoint: string;
  regions: string[];
  overall_reference_agreement: SegMetrics;
  overall_hansen_tree_agreement: BinaryMetrics;
  per_region: {
    region: string;
    reference_agreement: SegMetrics;
    hansen_tree_agreement: BinaryMetrics;
    valid_fraction: number;
    scene_ids: string[];
  }[];
  calibration: {
    temperature: number;
    ece_before: number;
    ece_after: number;
    reliability: { bin_low: number; bin_high: number; confidence: number; accuracy: number; count: number }[];
    pixels: number;
  } | null;
  notes: string[];
}

export interface Evaluation {
  id: string;
  experiment_id: string;
  regions: string[];
  status: string;
  job_id: string | null;
  created_at: string;
  result?: EvaluationResult;
  summary?: { mean_iou: number | null; overall_accuracy: number | null; hansen_f1: number | null };
}

export interface Segmentation {
  id: string;
  product_id: string;
  experiment_id: string;
  status: string;
  job_id: string | null;
  acquired: string | null;
  aoi_id: string | null;
  created_at: string;
  summary: {
    valid_fraction: number;
    valid_area_ha: number;
    tree_cover_ha: number;
    tree_cover_fraction_of_valid: number;
    tree_cover_uncertain_ha: number;
    class_areas_ha: Record<string, number>;
    mean_entropy: number | null;
    area_note: string;
  } | null;
}

export interface CategoryArea {
  pixels: number;
  hectares: number;
  fraction: number;
}

export interface ChangeHeadline {
  potential_loss_ha: number | null;
  potential_loss_uncertainty_ha: number | null;
  potential_gain_ha: number | null;
  n_loss_regions: number | null;
  n_gain_regions: number | null;
  valid_fraction_both_dates: number | null;
  tree_cover_before_ha: number | null;
  tree_cover_after_ha: number | null;
  evidence_counts: Record<string, number> | null;
}

export interface ChangeRun {
  id: string;
  aoi_id: string;
  aoi_name: string | null;
  before_id: string;
  after_id: string;
  before_acquired: string | null;
  after_acquired: string | null;
  extra_ids: string[];
  experiment_id: string;
  params: Record<string, number | boolean>;
  status: string;
  job_id: string | null;
  created_at: string;
  finished_at: string | null;
  headline: ChangeHeadline;
  summary?: {
    category_areas: Record<string, CategoryArea>;
    coregistration: { dx: number; dy: number; magnitude: number; response: number; applied: boolean };
    hansen_reference: string | null;
    worldcover_reference: string | null;
    checkpoint_sha256: string;
    calibrated: boolean;
    area_note: string;
    scene_ids_before: string[];
    scene_ids_after: string[];
    date_before: string[];
    date_after: string[];
    persistence_dates: string[][];
    params: Record<string, number | boolean>;
  };
}

export interface RegionProps {
  id: string;
  change_type: "potential_loss" | "potential_gain";
  evidence_level: "potential" | "spectrally_supported" | "corroborated_hansen";
  area_ha: number;
  area_uncertainty_ha: number;
  centroid_lon: number;
  centroid_lat: number;
  bbox: [number, number, number, number];
  pixel_count: number;
  p_tree_before: number | null;
  p_tree_after: number | null;
  delta_p_tree: number | null;
  delta_ndvi: number | null;
  delta_nbr: number | null;
  delta_ndmi: number | null;
  ndvi_before: number | null;
  ndvi_after: number | null;
  nbr_before: number | null;
  nbr_after: number | null;
  ndmi_before: number | null;
  ndmi_after: number | null;
  entropy_before: number | null;
  entropy_after: number | null;
  spectral_support_fraction: number | null;
  fire_like_fraction: number | null;
  hansen_loss_fraction?: number | null;
  persistence_fraction?: number | null;
  worldcover_tree_fraction?: number | null;
  possible_fire_related?: boolean;
  persistent?: boolean;
  distance_to_invalid_m: number | null;
  date_before: string;
  date_after: string;
  review_status?: string;
}

export interface Region {
  id: string;
  run_id: string;
  change_type: string;
  evidence_level: string;
  area_ha: number;
  area_uncertainty_ha: number;
  centroid_lon: number;
  centroid_lat: number;
  properties: RegionProps;
  review_status: string;
  analyst_notes: string;
  geometry?: GeoJSON.Geometry;
}

export interface RegionDetail extends Region {
  run: ChangeRun;
  run_summary: Record<string, unknown>;
  before: Product;
  after: Product;
}

export interface Job {
  id: string;
  type: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  message: string;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  log?: string;
}

export interface ExportRow {
  id: string;
  source_type: string;
  source_id: string;
  format: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

export interface Overview {
  aoi: AOI | null;
  observations: Product[];
  n_observations: number;
  latest_change: ChangeRun | null;
  recent_runs: ChangeRun[];
  model: Experiment | null;
  model_evaluation: Evaluation | null;
}

export interface TrainingRegion {
  name: string;
  role: string;
  center: [number, number];
  window: [string, string];
  description: string;
  built: boolean;
  bbox?: [number, number, number, number];
  label_source?: string;
  label_type?: string;
  label_report?: {
    labelled_fraction: number;
    class_counts: Record<string, number>;
    total_pixels: number;
    ignored_class_boundary?: number;
    ignored_hansen_recent_loss?: number;
    ignored_invalid_imagery?: number;
    ignored_reference_nodata_or_out_of_scope?: number;
  };
  selection?: { mode: string; valid_fraction: number };
  scene_ids?: string[];
  acquired?: string[];
}

export interface HistoryItem {
  type: "observation" | "change_run" | "segmentation" | "experiment" | "export";
  id: string;
  at: string;
  aoi_id: string | null;
  detail: Record<string, unknown>;
}
