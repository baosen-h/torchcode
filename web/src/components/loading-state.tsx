"use client";

import { useLanguage } from "@/lib/i18n";

export function LoadingState() {
  const { t } = useLanguage();
  return <div className="loading-state" role="status">{t("加载中…")}</div>;
}
