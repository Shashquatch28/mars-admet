// The session, as the frontend knows it (ADR-022): unknown, anonymous or signed in.
// The cookie is HttpOnly, so the only way to know is GET /auth/me. Any 401 from a
// gated call drops the app to anonymous in place (see setUnauthorizedHandler).
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { USING_API, fetchMe, login, logout, register, setUnauthorizedHandler } from "../data/client";
import { sessionStatus, type AuthMode, type SessionStatus } from "../domain/session";
import type { MeResponse } from "../types/contracts";

const ME_KEY = ["me"] as const;

interface AuthSession {
  status: SessionStatus;
  user: MeResponse | null;
  /** True while a sign-in, account creation or sign-out request is in flight. */
  busy: boolean;
  /** The last sign-in / account-creation failure; null once cleared or after success. */
  error: { status: number; message: string } | null;
  submit: (mode: AuthMode, email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  clearError: () => void;
}

const Ctx = createContext<AuthSession | null>(null);

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    enabled: USING_API,
    retry: false,
    staleTime: Infinity, // a session changes only through our own calls or a 401
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    setUnauthorizedHandler(() => qc.setQueryData(ME_KEY, null));
    return () => setUnauthorizedHandler(null);
  }, [qc]);

  const auth = useMutation({
    mutationFn: async (v: { mode: AuthMode; email: string; password: string }) => {
      if (v.mode === "register") await register(v.email, v.password); // returns no session: sign in next
      await login(v.email, v.password);
      return fetchMe();
    },
    onSuccess: (who) => qc.setQueryData(ME_KEY, who),
  });
  const out = useMutation({
    mutationFn: logout,
    onSuccess: () => qc.setQueryData(ME_KEY, null),
    // If the request failed we do not know the session is gone: ask again instead of guessing.
    onError: () => qc.invalidateQueries({ queryKey: ME_KEY }),
  });

  const { mutateAsync, reset } = auth;
  const submit = useCallback(
    async (mode: AuthMode, email: string, password: string) => {
      try {
        await mutateAsync({ mode, email: email.trim(), password });
        return true;
      } catch {
        return false; // the failure is exposed as `error`
      }
    },
    [mutateAsync],
  );
  const { mutateAsync: signOutAsync } = out;
  const signOut = useCallback(async () => {
    try {
      await signOutAsync();
    } catch {
      /* handled by onError */
    }
  }, [signOutAsync]);

  const status = sessionStatus({ usingApi: USING_API, pending: me.isPending, me: me.data });
  const value = useMemo<AuthSession>(
    () => ({
      status,
      user: me.data ?? null,
      busy: auth.isPending || out.isPending,
      error: auth.error ? { status: (auth.error as { status?: number }).status ?? 0, message: auth.error.message } : null,
      submit,
      signOut,
      clearError: reset,
    }),
    [status, me.data, auth.isPending, out.isPending, auth.error, submit, signOut, reset],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuthSession(): AuthSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuthSession must be used within AuthSessionProvider");
  return v;
}
