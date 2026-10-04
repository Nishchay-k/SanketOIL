import { fetchEventSource } from "@microsoft/fetch-event-source";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const runtimeConfig = window.__SANKET_CONFIG__ || {};
const API_BASE = runtimeConfig.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || "";
const AUTH_MODE = runtimeConfig.authMode || import.meta.env.VITE_AUTH_MODE || "demo";
const supabaseUrl = runtimeConfig.supabaseUrl || import.meta.env.VITE_SUPABASE_URL || "";
const supabaseAnonKey = runtimeConfig.supabaseAnonKey || import.meta.env.VITE_SUPABASE_ANON_KEY || "";
const supabase: SupabaseClient | null = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

function authConfigurationError() {
  if (AUTH_MODE === "supabase" && !supabase) {
    return new Error("Supabase sign-in is not configured. Set the VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY environment variables.");
  }
  return null;
}

async function authorizationHeaders(headers?: HeadersInit) {
  const result = new Headers(headers || {});
  if (AUTH_MODE === "supabase") {
    const error = authConfigurationError();
    if (error) throw error;
    const { data, error: sessionError } = await supabase!.auth.getSession();
    if (sessionError) throw sessionError;
    if (data.session?.access_token) result.set("Authorization", `Bearer ${data.session.access_token}`);
  }
  return result;
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = await authorizationHeaders(options.headers);
  const response = await fetch(API_BASE + path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.error?.message || "The drilling data request could not be completed.";
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return payload as T;
}

function queryString(values: Record<string, unknown> = {}) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  authMode: AUTH_MODE,
  signIn: async (email: string, password: string) => {
    const error = authConfigurationError();
    if (error) throw error;
    const { data, error: signInError } = await supabase!.auth.signInWithPassword({ email, password });
    if (signInError) throw signInError;
    return data;
  },
  signOut: async () => {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  },
  getSession: async () => {
    if (!supabase) return null;
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    return data.session;
  },
  bootstrap: () => request("/api/bootstrap"),
  health: () => request("/api/health"),
  formations: () => request("/api/formations"),
  wells: (filters?: Record<string, unknown>) => request("/api/wells" + queryString(filters)),
  addWell: (input: Record<string, unknown>) => request("/api/wells", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }),
  search: (query: string, limit?: number) => request("/api/search" + queryString({ q: query, limit: limit || 20 })),
  documents: () => request("/api/documents"),
  document: (documentId: string) => request("/api/documents/" + encodeURIComponent(documentId)),
  documentExtractions: (documentId: string) => request("/api/documents/" + encodeURIComponent(documentId) + "/extractions"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/documents", { method: "POST", body: form });
  },
  well: (wellCode: string) => request("/api/wells/" + encodeURIComponent(wellCode)),
  nearby: (wellCode: string, radius: number, depth: number, formation: string) => request("/api/wells/nearby" + queryString({ well_id: wellCode, radius_km: radius, depth, formation })),
  correlation: (wellCode: string, radius: number, depth: number, formation: string) => request("/api/correlation" + queryString({ well_id: wellCode, radius_km: radius, depth, formation })),
  alerts: (wellCode?: string, status?: string) => request("/api/alerts" + queryString({ well_id: wellCode, status })),
  updateAlert: (alertId: string, action: string) => request("/api/alerts/" + encodeURIComponent(alertId) + "/" + encodeURIComponent(action), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  }),
  events: (filters?: Record<string, unknown>) => request("/api/events" + queryString(filters)),
  predictRisk: (input: Record<string, unknown>) => request("/api/risk/predict", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }),
  telemetry: (wellCode: string) => request("/api/telemetry" + queryString({ well_id: wellCode })),
  sendTelemetry: (input: Record<string, unknown>) => request("/api/telemetry", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }),
  streamTelemetry: (wellCode: string, onTelemetry: (data: any) => void, onAlert: (data: any) => void) => {
    const controller = new AbortController();
    void (async () => {
      const headers = await authorizationHeaders();
      await fetchEventSource(API_BASE + "/api/telemetry/stream" + queryString({ well_id: wellCode }), {
        headers: Object.fromEntries(headers.entries()),
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(response) {
          if (!response.ok) throw new Error(response.status === 401 ? "Sign in again to receive live telemetry." : "The telemetry stream could not be opened.");
        },
        onmessage(message) {
          if (!message.data) return;
          try {
            const data = JSON.parse(message.data);
            if (message.event === "telemetry") onTelemetry(data);
            if (message.event === "alert") onAlert(data);
          } catch (error) {
            console.error("Could not read a telemetry event", error);
          }
        },
        onclose() {
          if (!controller.signal.aborted) throw new Error("Telemetry connection closed; reconnecting.");
        },
        onerror(error) {
          if (controller.signal.aborted) throw error;
          return 2500;
        },
      }).catch((error) => {
        if (!controller.signal.aborted) console.error("Telemetry stream stopped", error);
      });
    })().catch((error) => {
      if (!controller.signal.aborted) console.error("Could not start the telemetry stream", error);
    });
    return { close: () => controller.abort() };
  },
};
