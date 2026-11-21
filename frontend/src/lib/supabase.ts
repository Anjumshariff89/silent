// Supabase Auth client (browser only). Enabled when NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set
// in frontend/.env.local. Only the public anon key is used here; the service-role key must never reach the browser.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const SUPABASE_ENABLED = Boolean(URL && ANON_KEY);

let client: SupabaseClient | null = null;

export function supabase(): SupabaseClient | null {
  if (!SUPABASE_ENABLED || typeof window === "undefined") return null;
  if (!client) {
    client = createClient(URL as string, ANON_KEY as string, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storageKey: "silent-auth" },
    });
  }
  return client;
}
