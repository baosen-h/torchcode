"use client";

import { translate as t } from "./i18n";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, TaskDetails } from "./api";

type Draft = { code: string; notes: string; draft_updated_at: string };
type SaveState = "saved" | "pending" | "saving" | "error";

function readDraft(task: TaskDetails): Draft {
  const fallback = { code: task.progress.code ?? task.initial_code, notes: task.progress.notes, draft_updated_at: task.progress.draft_updated_at };
  try {
    const cached = JSON.parse(localStorage.getItem(`torchcode_draft_${task.id}`) || "null");
    if (typeof cached?.code === "string" && typeof cached?.notes === "string"
      && Date.parse(cached.draft_updated_at) > (Date.parse(fallback.draft_updated_at) || 0)) return cached;
  } catch { /* The database remains the primary copy. */ }
  return fallback;
}

export function useTaskDraft(task: TaskDetails) {
  const [draft, setDraft] = useState(() => readDraft(task));
  const [saveState, setSaveState] = useState<SaveState>(() => draft.draft_updated_at === task.progress.draft_updated_at ? "saved" : "pending");
  const [saveError, setSaveError] = useState("");
  const [storageWarning, setStorageWarning] = useState("");
  const latest = useRef(draft);
  const savedTimestamp = useRef(task.progress.draft_updated_at);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const isMounted = useRef(true);

  const persist = useCallback((snapshot: Draft) => {
    const operation = queue.current.catch(() => undefined).then(() => api(`/tasks/${task.id}/progress`, {
      method: "PATCH", body: JSON.stringify(snapshot),
    }));
    queue.current = operation;
    return operation;
  }, [task.id]);

  const flush = useCallback(async () => {
    const snapshot = latest.current;
    if (snapshot.draft_updated_at === savedTimestamp.current) return queue.current;
    if (isMounted.current) setSaveState("saving");
    try {
      await persist(snapshot);
      savedTimestamp.current = snapshot.draft_updated_at;
      if (isMounted.current && latest.current.draft_updated_at === snapshot.draft_updated_at) {
        setSaveState("saved");
        setSaveError("");
      }
    } catch (error) {
      if (isMounted.current) {
        setSaveState("error");
        setSaveError(errorMessage(error));
      }
      throw error;
    }
  }, [persist]);

  function updateDraft(changes: Partial<Pick<Draft, "code" | "notes">>) {
    const previousTime = Date.parse(latest.current.draft_updated_at) || 0;
    const next = { ...latest.current, ...changes, draft_updated_at: new Date(Math.max(Date.now(), previousTime + 1)).toISOString() };
    latest.current = next;
    setDraft(next);
    setSaveState("pending");
    try {
      localStorage.setItem(`torchcode_draft_${task.id}`, JSON.stringify(next));
      localStorage.setItem(`torchcode_code_${task.id}`, next.code);
      setStorageWarning("");
    } catch { setStorageWarning(t("浏览器本地备份不可用，请确认数据库保存成功后再离开。")); }
  }

  useEffect(() => {
    if (draft.draft_updated_at === savedTimestamp.current) return;
    const timeout = setTimeout(() => { void flush().catch(() => undefined); }, 700);
    return () => clearTimeout(timeout);
  }, [draft, flush]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      if (latest.current.draft_updated_at !== savedTimestamp.current) void persist(latest.current).catch(() => undefined);
    };
  }, [persist]);

  return { draft, updateDraft, flush, saveState, saveError, storageWarning };
}
