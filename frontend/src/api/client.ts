export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {}),
  del: <T>(p: string) => request<T>("DELETE", p),
};

export const tileUrl = (source: string, ref: string, render?: string, band?: string) => {
  const q = new URLSearchParams();
  if (render) q.set("render", render);
  if (band) q.set("band", band);
  const qs = q.toString();
  return `${window.location.origin}/api/tiles/${source}/${ref}/{z}/{x}/{y}.png${qs ? `?${qs}` : ""}`;
};

export const chipUrl = (productId: string, bbox: number[], render = "truecolor", size = 384, band?: string) =>
  `/api/products/${productId}/chip.png?bbox=${bbox.map((v) => v.toFixed(6)).join(",")}&render=${render}&size=${size}${
    band ? `&band=${band}` : ""
  }`;
