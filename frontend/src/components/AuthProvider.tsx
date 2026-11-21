"use client";

// Session provider. With Supabase Auth it follows the Supabase session (sign-in, token refresh, sign-out) and
// mirrors the current access token into the API client; without Supabase it uses the local admin token.
import { createContext, useContext, useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";
import { supabase } from "@/lib/supabase";

interface AuthState {
  ready: boolean;          // initial session check finished
  token: string | null;    // current access token (null = signed out)
  email: string | null;
}

const AuthContext = createContext<AuthState>({ ready: false, token: null, email: null });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ ready: false, token: null, email: null });

  useEffect(() => {
    const sb = supabase();
    if (!sb) {
      setState({ ready: true, token: getToken(), email: null });
      return;
    }
    let active = true;
    sb.auth.getSession().then(({ data }) => {
      if (!active) return;
      const s = data.session;
      setToken(s?.access_token ?? null);
      setState({ ready: true, token: s?.access_token ?? null, email: s?.user.email ?? null });
    });
    const { data } = sb.auth.onAuthStateChange((_event, s) => {
      setToken(s?.access_token ?? null);
      setState({ ready: true, token: s?.access_token ?? null, email: s?.user.email ?? null });
    });
    return () => { active = false; data.subscription.unsubscribe(); };
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
