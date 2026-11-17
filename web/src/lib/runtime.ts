export type PythonEnvironment = {
  id: string;
  name: string;
  prefix?: string;
  python?: string;
  version?: string;
  has_python: boolean;
  is_backend?: boolean;
  can_install?: boolean;
};

export type EnvironmentJob = {
  id: string;
  title: string;
  status: "running" | "succeeded" | "failed";
  message: string;
  log: string;
  started_at: number;
  finished_at: number | null;
};

export type RuntimeSelection = { selected: PythonEnvironment; error: string };
export type RuntimeState = RuntimeSelection & {
  environments: PythonEnvironment[];
  conda_available: boolean;
  discovery_error: string;
  job: EnvironmentJob | null;
  active_runs: number;
};

export function environmentReturnPath(value: string | null) {
  if (value === "/problems" || value?.startsWith("/problems?")) return value;
  if (value && /^\/problems\/[A-Za-z0-9_-]+(?:\?[^#\r\n]*)?$/.test(value)) return value;
  return "/problems";
}
