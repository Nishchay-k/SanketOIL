/// <reference types="vite/client" />

interface Window {
  __SANKET_CONFIG__?: {
    apiBaseUrl?: string;
    authMode?: "demo" | "supabase";
    supabaseUrl?: string;
    supabaseAnonKey?: string;
  };
}
