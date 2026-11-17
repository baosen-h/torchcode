"use client";

import { useLanguage } from "@/lib/i18n";

import { useEffect, useId, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertCircle, BookOpen, FolderTree, Settings2, X } from "lucide-react";
import { Difficulty } from "@/lib/api";
import { useLibrary } from "./library-provider";

export function SiteHeader() {
  const { t, locale, setLocale } = useLanguage();
  const pathname = usePathname();
  const { warning } = useLibrary();
  return <>
    <header className="site-header">
      <Link href="/problems" className="brand">TorchCode<span>{t("个人题库")}</span></Link>
      <nav aria-label={t("主导航")}>
        <Link href="/problems" className={pathname.startsWith("/problems") ? "active" : ""}><BookOpen size={16} />{t("题库")}</Link>
        <Link href="/categories" className={pathname === "/categories" ? "active" : ""}><FolderTree size={16} />{t("分类管理")}</Link>
        <Link href="/environments" className={pathname === "/environments" ? "active" : ""}><Settings2 size={16} />{t("运行环境")}</Link>
      </nav>
      <label className="language-picker"><span className="visually-hidden">{t("切换界面语言")}</span><select aria-label={t("切换界面语言")} value={locale} onChange={(event) => setLocale(event.target.value as "en" | "zh-CN")}><option value="zh-CN">中文</option><option value="en">English</option></select></label>
      <span className="header-caption">{t("记录问题，积累解法")}</span>
    </header>
    {warning && <div className="migration-warning" role="status">{t(warning)}</div>}
  </>;
}

export function Modal({ title, children, onClose, isBusy = false, wide = false }: {
  title: string; children: React.ReactNode; onClose: () => void; isBusy?: boolean; wide?: boolean;
}) {
  const { t } = useLanguage();
  const reference = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = reference.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={reference} aria-labelledby={titleId} className={`modal ${wide ? "modal-wide" : ""}`}
    onCancel={(event) => { event.preventDefault(); if (!isBusy) onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget && !isBusy) onClose(); }}>
    <div className="modal-content">
      <div className="modal-heading"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label={t("关闭")} onClick={onClose} disabled={isBusy}><X size={20} /></button></div>
      {children}
    </div>
  </dialog>;
}

export function DifficultyBadge({ difficulty }: { difficulty: Difficulty }) {
  const { t } = useLanguage();
  return <span className={`difficulty difficulty-${difficulty.toLowerCase() || "none"}`}>{difficulty || t("未设置")}</span>;
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useLanguage();
  if (!message) return null;
  return <div className="error-notice" role="alert"><AlertCircle size={17} /><span>{t(message)}</span>{onRetry && <button className="text-button" onClick={onRetry}>{t("重试")}</button>}</div>;
}

export function CategoryPicker({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) {
  const { t, categoryLabel } = useLanguage();
  const { categories } = useLibrary();
  if (!categories.length) return <p className="muted">{t("还没有分类，可以先新增一个。")}</p>;
  return <div className="category-picker">{categories.map((category) => <label key={category.id} className={`category-choice ${selected.includes(category.id) ? "selected" : ""}`}>
    <input type="checkbox" checked={selected.includes(category.id)} onChange={() => onChange(selected.includes(category.id)
      ? selected.filter((id) => id !== category.id) : [...selected, category.id])} />{categoryLabel(category.name)}
  </label>)}</div>;
}
