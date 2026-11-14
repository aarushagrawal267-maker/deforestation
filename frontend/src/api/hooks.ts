import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AOI,
  ChangeRun,
  Evaluation,
  Experiment,
  ExportRow,
  HistoryItem,
  Job,
  Overview,
  Product,
  Region,
  RegionDetail,
  Scene,
  Segmentation,
  TrainingRegion,
} from "./types";

const ACTIVE = new Set(["queued", "running"]);
const poll = (active: boolean) => (active ? 2000 : false);

export const useSystem = () => useQuery({ queryKey: ["system"], queryFn: () => api.get<Record<string, unknown>>("/system") });
export const useSettings = () =>
  useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<{ active_aoi_id: string | null; active_experiment_id: string | null }>("/settings"),
  });
export const useOverview = (aoiId?: string | null) =>
  useQuery({
    queryKey: ["overview", aoiId],
    queryFn: () => api.get<Overview>(`/overview${aoiId ? `?aoi_id=${aoiId}` : ""}`),
    refetchInterval: (q) => poll(!!q.state.data?.recent_runs.some((r) => ACTIVE.has(r.status))),
  });
export const useAOIs = () => useQuery({ queryKey: ["aois"], queryFn: () => api.get<AOI[]>("/aois") });
export const useProducts = (aoiId?: string | null) =>
  useQuery({
    queryKey: ["products", aoiId],
    queryFn: () => api.get<Product[]>(`/products${aoiId ? `?aoi_id=${aoiId}` : ""}`),
    enabled: !!aoiId,
  });
export const useExperiments = () =>
  useQuery({
    queryKey: ["experiments"],
    queryFn: () => api.get<Experiment[]>("/experiments"),
    refetchInterval: (q) => poll(!!q.state.data?.some((e) => ACTIVE.has(e.status))),
  });
export const useExperiment = (id?: string | null) =>
  useQuery({
    queryKey: ["experiment", id],
    queryFn: () => api.get<Experiment>(`/experiments/${id}`),
    enabled: !!id,
    refetchInterval: (q) => poll(ACTIVE.has(q.state.data?.status ?? "")),
  });
export const useEvaluations = (experimentId?: string | null) =>
  useQuery({
    queryKey: ["evaluations", experimentId],
    queryFn: () => api.get<Evaluation[]>(`/evaluations${experimentId ? `?experiment_id=${experimentId}` : ""}`),
    refetchInterval: (q) => poll(!!q.state.data?.some((e) => ACTIVE.has(e.status))),
  });
export const useEvaluation = (id?: string | null) =>
  useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api.get<Evaluation>(`/evaluations/${id}`),
    enabled: !!id,
    refetchInterval: (q) => poll(ACTIVE.has(q.state.data?.status ?? "")),
  });
export const useSegmentations = (aoiId?: string | null) =>
  useQuery({
    queryKey: ["segmentations", aoiId],
    queryFn: () => api.get<Segmentation[]>(`/segmentations${aoiId ? `?aoi_id=${aoiId}` : ""}`),
    refetchInterval: (q) => poll(!!q.state.data?.some((e) => ACTIVE.has(e.status))),
  });
export const useChangeRuns = (aoiId?: string | null) =>
  useQuery({
    queryKey: ["change-runs", aoiId],
    queryFn: () => api.get<ChangeRun[]>(`/change-runs${aoiId ? `?aoi_id=${aoiId}` : ""}`),
    refetchInterval: (q) => poll(!!q.state.data?.some((e) => ACTIVE.has(e.status))),
  });
export const useChangeRun = (id?: string | null) =>
  useQuery({
    queryKey: ["change-run", id],
    queryFn: () => api.get<ChangeRun>(`/change-runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => poll(ACTIVE.has(q.state.data?.status ?? "")),
  });
export const useRegionsGeo = (runId?: string | null, enabled = true) =>
  useQuery({
    queryKey: ["regions-geo", runId],
    queryFn: () => api.get<GeoJSON.FeatureCollection>(`/change-runs/${runId}/regions`),
    enabled: !!runId && enabled,
  });
export const useRegions = (params: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
  return useQuery({ queryKey: ["regions", params], queryFn: () => api.get<Region[]>(`/regions?${q}`) });
};
export const useRegion = (id?: string) =>
  useQuery({ queryKey: ["region", id], queryFn: () => api.get<RegionDetail>(`/regions/${id}`), enabled: !!id });
export const useJobs = () =>
  useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: (q) => poll(!!q.state.data?.some((j) => ACTIVE.has(j.status))),
  });
export const useJob = (id?: string | null) =>
  useQuery({
    queryKey: ["job", id],
    queryFn: () => api.get<Job>(`/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && !ACTIVE.has(q.state.data.status) ? false : 1500),
  });
export const useDatasets = () => useQuery({ queryKey: ["datasets"], queryFn: () => api.get<Record<string, any>>("/datasets") });
export const useTrainingRegions = () =>
  useQuery({
    queryKey: ["training-regions"],
    queryFn: () => api.get<{ label_year: number; size_deg: number; regions: TrainingRegion[] }>("/datasets/regions"),
  });
export const useHistory = () => useQuery({ queryKey: ["history"], queryFn: () => api.get<HistoryItem[]>("/history") });
export const useExports = () => useQuery({ queryKey: ["exports"], queryFn: () => api.get<ExportRow[]>("/exports") });
export const useCategories = () =>
  useQuery({
    queryKey: ["categories"],
    queryFn: () =>
      api.get<{ categories: { id: number; key: string; name: string; color: string }[]; default_params: Record<string, number | boolean> }>(
        "/change/categories",
      ),
    staleTime: Infinity,
  });
export const useSceneSearch = () =>
  useMutation({
    mutationFn: (b: { aoi_id: string; start: string; end: string; max_cloud: number; provider: string }) =>
      api.post<Scene[]>("/catalog/search", b),
  });

export function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}
