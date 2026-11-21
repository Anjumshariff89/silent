import { supabase } from "./supabase";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN_KEY = "lace_token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

/** Current access token: the Supabase session's (refreshed automatically when expired) or the local admin token. */
export async function accessToken(): Promise<string | null> {
  const sb = supabase();
  if (!sb) return getToken();
  const { data } = await sb.auth.getSession();
  const token = data.session?.access_token ?? null;
  setToken(token);
  return token;
}

export async function hasSession(): Promise<boolean> {
  return Boolean(await accessToken());
}

export async function signOut(): Promise<void> {
  const sb = supabase();
  if (sb) await sb.auth.signOut();
  setToken(null);
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e as { msg?: string }).msg ?? "invalid").join("; ");
  }
  return fallback;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth")) {
    await signOut();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detailOf(body, `HTTP ${res.status}`));
  }
  return (await res.json()) as T;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/** Authenticated file download (JSON/PDF evidence). */
export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${(await accessToken()) ?? ""}` } });
  if (!res.ok) throw new ApiError(res.status, `Download failed (HTTP ${res.status})`);
  triggerDownload(await res.blob(), filename);
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function wsUrl(): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/live?token=${encodeURIComponent(getToken() ?? "")}`;
}
