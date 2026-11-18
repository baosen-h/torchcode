"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, errorMessage, Library, migrateLegacyRecords } from "@/lib/api";

type LibraryContextValue = Library & {
  isLoading: boolean;
  error: string;
  warning: string;
  refresh: () => Promise<void>;
};

const LibraryContext = createContext<LibraryContextValue | null>(null);

export function LibraryProvider({ children }: { children: React.ReactNode }) {
  const [library, setLibrary] = useState<Library>({ database_id: "", categories: [], tasks: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const current = ++generation.current;
    try {
      const identity = await api<{ database_id: string; api_version?: number }>("/health");
      if ((identity.api_version || 0) < 3) throw new Error("后台版本较旧，请重新运行启动器以更新服务。");
      const migrationWarning = await migrateLegacyRecords(identity.database_id);
      const nextLibrary = await api<Library>("/library");
      if (current !== generation.current) return;
      setLibrary(nextLibrary);
      setWarning(migrationWarning);
      setError("");
    } catch (error) {
      if (current === generation.current) setError(errorMessage(error));
      throw error;
    } finally {
      if (current === generation.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  useEffect(() => {
    const onFocus = () => { void refresh().catch(() => undefined); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  return <LibraryContext.Provider value={{ ...library, isLoading, error, warning, refresh }}>{children}</LibraryContext.Provider>;
}

export function useLibrary() {
  const value = useContext(LibraryContext);
  if (!value) throw new Error("LibraryProvider is required");
  return value;
}
