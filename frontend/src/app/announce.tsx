// The one polite live region (WCAG 4.1.3). `announce("text")` from anywhere; the shell mounts the region.
// The same text said twice in a row is still read: each message is rendered under a fresh key.
// The latest text is also exposed for the status bar to show (ADR-034 item 4): sighted users get the same
// confirmation the live region gives a screen reader, as plain text with no timer and no animation.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface Announcer {
  announce: (message: string) => void;
  /** The most recent announcement, or null before the first one. Shown, never re-announced. */
  last: string | null;
}

const Ctx = createContext<Announcer>({ announce: () => {}, last: null });

export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<{ id: number; text: string } | null>(null);
  const announce = useCallback((text: string) => setMessage((m) => ({ id: (m?.id ?? 0) + 1, text })), []);
  const value = useMemo(() => ({ announce, last: message?.text ?? null }), [announce, message]);
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

/** The latest announcement as text for the status bar. */
export function useLastAnnouncement(): string | null {
  return useContext(Ctx).last;
}
