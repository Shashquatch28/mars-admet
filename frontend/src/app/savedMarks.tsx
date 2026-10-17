// What this browser session has already saved, so the same prediction or batch is not saved
// twice by a second click. Keys come from domain/save.ts. The marks belong to the account:
// they are dropped the moment the session is not signed in (sign-out, a 401, a deleted
// account), because a mark from another account must not say "saved" here.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuthSession } from "./authSession";

interface SavedMarks {
  isSaved: (key: string) => boolean;
  mark: (key: string) => void;
}

const Ctx = createContext<SavedMarks | null>(null);

export function SavedMarksProvider({ children }: { children: ReactNode }) {
  const { status } = useAuthSession();
  const [keys, setKeys] = useState<ReadonlySet<string>>(new Set());

  useEffect(() => {
    if (status !== "signed_in") setKeys((k) => (k.size ? new Set() : k));
  }, [status]);

  const isSaved = useCallback((key: string) => keys.has(key), [keys]);
  const mark = useCallback((key: string) => setKeys((k) => new Set(k).add(key)), []);
  const value = useMemo(() => ({ isSaved, mark }), [isSaved, mark]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSavedMarks(): SavedMarks {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSavedMarks must be used within SavedMarksProvider");
  return v;
}
