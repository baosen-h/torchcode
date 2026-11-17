"use client";

import { useLanguage } from "@/lib/i18n";

import { Check, ChevronDown, Play, X } from "lucide-react";
import { Progress } from "@/lib/api";

export type SubmissionResponse = {
  success: boolean;
  mode?: "run" | "tests";
  warning?: string;
  environment?: { id: string; name: string };
  error?: string;
  traceback?: string;
  passed: number;
  total: number;
  total_time_ms?: number;
  progress?: Progress;
  tests: { name: string; code: string; passed: boolean; time_ms: number; error_msg: string | null;
    error_traceback: string | null; stdout: string; stderr: string }[];
  stdout: string;
  stderr: string;
};

export function TestResults({ results, isSubmitting }: { results: SubmissionResponse | null; isSubmitting: boolean }) {
  const { t } = useLanguage();
  if (isSubmitting) return <div className="empty-state">{t("正在执行代码和测试，请稍候…")}</div>;
  if (!results) return <div className="empty-state"><Play size={34} /><p>{t("点击右上角运行按钮，在这里查看输出与测试结果。")}</p></div>;
  const isRunOnly = results.mode === "run";
  const verdict = results.success ? isRunOnly ? t("运行成功") : t("Accepted · 测试通过") : results.error ? t("执行失败") : t("测试未通过");
  return <div className="test-results">
    <div className={`test-verdict ${results.success ? "text-success" : "text-error"}`}>{verdict}</div>
    <p className="muted">{isRunOnly ? t("仅运行代码，未进行测试判定") : t("通过 {0}/{1} 个测试", results.passed, results.total)}{results.total_time_ms !== undefined ? ` · ${results.total_time_ms.toFixed(1)} ms` : ""}</p>
    {results.environment && <p className="muted runtime-result">{t("运行环境：{0}", t(results.environment.name))}</p>}
    {results.warning && <div className="execution-warning">{t(results.warning)}</div>}
    {results.error && <div className="execution-error"><strong>{t(results.error)}</strong>{results.traceback && <pre>{results.traceback}</pre>}</div>}
    {results.tests?.map((test, index) => <div className="test-case" key={index}>
      <div className="test-case-heading">{test.passed ? <Check className="text-success" size={18} /> : <X className="text-error" size={18} />}<span>Case {index + 1}: {test.name}</span><span className="muted">{test.time_ms.toFixed(1)} ms</span></div>
      {test.code && <details><summary><ChevronDown size={14} />{t("测试代码")}</summary><pre>{test.code}</pre></details>}
      {test.error_msg && <div className="execution-error"><pre>{t(test.error_msg)}</pre>{test.error_traceback && <pre>{test.error_traceback}</pre>}</div>}
      {test.stdout && <div className="test-output"><span className="muted">{t("Standard output")}</span><pre>{test.stdout}</pre></div>}
      {test.stderr && <div className="test-output"><span className="muted">{t("Standard error")}</span><pre>{test.stderr}</pre></div>}
    </div>)}
    {results.stdout && <div className="test-output"><h3>{t("Global output")}</h3><pre>{results.stdout}</pre></div>}
    {results.stderr && <div className="test-output"><h3>{t("Standard error")}</h3><pre>{results.stderr}</pre></div>}
    {isRunOnly && results.success && !results.stdout && !results.stderr && <p className="muted">{t("运行完成，未产生标准输出。可以使用 print(...) 查看中间结果。")}</p>}
  </div>;
}
