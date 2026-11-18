
import { translate as t } from "./i18n";
export type TaskStatus = "todo" | "attempted" | "solved";
export type Difficulty = "" | "Easy" | "Medium" | "Hard";

export type Progress = {
  status: TaskStatus;
  completion_source: "manual" | "tests" | "legacy" | null;
  solved_at: string | null;
  draft_updated_at: string;
  updated_at: string;
  last_opened_at: string | null;
};

export type Category = { id: string; name: string; position: number };
export type TestCase = { id: string; name: string; code: string; enabled: boolean };
export type Task = {
  id: string;
  problem_number: number;
  title: string;
  difficulty: Difficulty;
  source: "builtin" | "custom";
  source_url: string;
  category_ids: string[];
  created_at: string;
  updated_at: string;
  search_text: string;
  progress: Progress;
};

export type TaskDetails = Omit<Task, "search_text"> & {
  hint: string;
  description: string;
  initial_code: string;
  test_cases: TestCase[];
  tests_revision: number;
  progress: Progress & { code: string | null; notes: string };
};

export type TaskInput = {
  title: string;
  description: string;
  difficulty: Difficulty;
  initial_code: string;
  source_url: string;
  category_ids: string[];
};

export type Library = { database_id: string; categories: Category[]; tasks: Task[] };

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    cache: "no-store",
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (Array.isArray(detail)) throw new Error(detail.map((item) => item.msg).join("\n"));
    throw new Error(t("请求失败（{0}），请检查后端服务是否已启动。", response.status));
  }
  if (data === null) throw new Error(t("后端未返回有效数据，请检查 API 地址。 "));
  return data as T;
}

export function errorMessage(error: unknown) {
  if (error instanceof TypeError) return t("无法连接后端，请启动 API 服务后重试。");
  if (error instanceof Error) return error.message;
  return t("操作失败，请重试。");
}

export async function migrateLegacyRecords(databaseId: string): Promise<string> {
  try {
    const marker = `torchcode_migrated_${databaseId}`;
    if (localStorage.getItem(marker)) return "";
    const saved = JSON.parse(localStorage.getItem("torchcode_solved_tasks") || "{}");
    const solved_ids = Object.keys(saved).filter((key) => saved[key] === true);
    const drafts: Record<string, string> = {};
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith("torchcode_code_")) {
        const value = localStorage.getItem(key);
        if (value !== null) drafts[key.slice("torchcode_code_".length)] = value;
      }
    }
    if (solved_ids.length || Object.keys(drafts).length) {
      await api("/library/migrate", { method: "POST", body: JSON.stringify({ solved_ids, drafts }) });
    }
    localStorage.setItem(marker, "done");
    return "";
  } catch (error) {
    return t("旧记录尚未迁移成功，原始记录仍保留：{0}", errorMessage(error));
  }
}

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "未开始", attempted: "进行中", solved: "已解决",
};

export const COMPLETION_LABELS = { manual: "自行确认", tests: "测试通过", legacy: "历史完成记录" };

export function safeReturnPath(value: string | null) {
  if (value === "/problems" || value?.startsWith("/problems?")) return value;
  return "/problems";
}
