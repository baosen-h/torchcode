"use client";

import { useRef, useState } from "react";
import { api, errorMessage, TaskDetails, TestCase } from "./api";

type LocalSuite = { test_cases: TestCase[]; base_revision: number };

function readLocalSuite(task: TaskDetails): TestCase[] {
  try {
    const cached: LocalSuite = JSON.parse(localStorage.getItem(`torchcode_tests_${task.id}`) || "null");
    if (cached?.base_revision === task.tests_revision && Array.isArray(cached.test_cases)
      && cached.test_cases.every((test) => typeof test.id === "string" && typeof test.name === "string"
        && typeof test.code === "string" && typeof test.enabled === "boolean")) return cached.test_cases;
  } catch { /* Tests saved in the database remain available. */ }
  return task.test_cases || [];
}

export function useTestCases(task: TaskDetails, onSaved: (task: TaskDetails) => void) {
  const [cases, setCases] = useState(() => readLocalSuite(task));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef(cases);
  const savedCases = useRef(task.test_cases || []);
  const revision = useRef(task.tests_revision || 0);
  const operation = useRef<Promise<TaskDetails> | null>(null);
  const isDirty = JSON.stringify(cases) !== JSON.stringify(savedCases.current);

  function cache(nextCases: TestCase[]) {
    try {
      localStorage.setItem(`torchcode_tests_${task.id}`, JSON.stringify({ test_cases: nextCases, base_revision: revision.current }));
    } catch { /* Explicit database saving remains available. */ }
  }

  function change(nextCases: TestCase[]) {
    latest.current = nextCases;
    setCases(nextCases);
    setError("");
    cache(nextCases);
  }

  function discard() {
    change(savedCases.current);
    try { localStorage.removeItem(`torchcode_tests_${task.id}`); } catch { /* Optional browser cache. */ }
  }

  async function save(): Promise<TaskDetails> {
    if (operation.current) return operation.current;
    if (JSON.stringify(latest.current) === JSON.stringify(savedCases.current)) {
      return { ...task, test_cases: latest.current, tests_revision: revision.current };
    }
    const snapshot = latest.current;
    setIsSaving(true);
    setError("");
    const request = api<TaskDetails>(`/tasks/${task.id}/tests`, {
      method: "PUT", body: JSON.stringify({ test_cases: snapshot, expected_revision: revision.current }),
    });
    operation.current = request;
    try {
      const saved = await request;
      revision.current = saved.tests_revision;
      savedCases.current = saved.test_cases;
      if (latest.current === snapshot) {
        latest.current = saved.test_cases;
        setCases(saved.test_cases);
        try { localStorage.removeItem(`torchcode_tests_${task.id}`); } catch { /* Optional browser cache. */ }
      } else { cache(latest.current); }
      onSaved(saved);
      return saved;
    } catch (error) {
      setError(errorMessage(error));
      throw error;
    } finally {
      setIsSaving(false);
      operation.current = null;
    }
  }

  return { cases, change, save, discard, isDirty, isSaving, error };
}
