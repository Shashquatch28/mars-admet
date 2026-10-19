// The one polite live region (WCAG 4.1.3). `announce("text")` from anywhere; the shell mounts the region.
// The same text said twice in a row is still read: each message is rendered under a fresh key.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface Announcer {
  announce: (message: string) => void;
}

const Ctx = createContext<Announcer>({ announce: () => {} });

export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<{ id: number; text: string } | null>(null);
  const announce = useCallback((text: string) => setMessage((m) => ({ id: (m?.id ?? 0) + 1, text })), []);
  const value = useMemo(() => ({ announce }), [announce]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {message && <span key={message.id}>{message.text}</span>}
      </div>
    </Ctx.Provider>
  );
}

export function useAnnounce(): (message: string) => void {
  return useContext(Ctx).announce;
}
