// A yes/no choice a person makes about their own view (a panel folded away), remembered in this browser only.
// Storage can be missing or blocked (private windows, site data cleared), so every access is guarded and the page
// works the same without it: the flag just starts at false each time.
import { useCallback, useState } from "react";

export function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function writeFlag(key: string, on: boolean): void {
  try {
    if (on) window.localStorage.setItem(key, "1");
    else window.localStorage.removeItem(key);
  } catch {
    /* not remembered; nothing else depends on it */
  }
}

export function usePersistedFlag(key: string): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState<boolean>(() => readFlag(key));
  const set = useCallback(
    (next: boolean) => {
      setOn(next);
      writeFlag(key, next);
    },
    [key],
  );
  return [on, set];
}
