"use client";

import { useLanguage } from "@/lib/i18n";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { RuntimeSelection } from "@/lib/runtime";

export function EnvironmentPicker() {
  const { t } = useLanguage();
  const pathname = usePathname();
  const parameters = useSearchParams();
  const [runtime, setRuntime] = useState<RuntimeSelection | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => { void api<RuntimeSelection>("/environments/current", { signal: controller.signal }).then(setRuntime).catch(() => undefined); };
    refresh();
    window.addEventListener("focus", refresh);
    return () => { controller.abort(); window.removeEventListener("focus", refresh); };
  }, []);
  const returnTo = pathname + (parameters.size ? `?${parameters}` : "");
  return <Link className={`runtime-picker ${runtime?.error ? "text-error" : ""}`} href={`/environments?returnTo=${encodeURIComponent(returnTo)}`} title={runtime?.error || t("切换运行环境或安装依赖")}>
    <Settings2 size={13} /><span>{t("环境：{0}", (runtime?.selected.name ? t(runtime.selected.name) : "") || t("加载中…"))}</span>
  </Link>;
}
