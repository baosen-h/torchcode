"use client";

import { ChangeEvent, ClipboardEvent, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { ErrorNotice } from "./ui";

const MAX_IMAGE_BYTES = 1024 * 1024;
const MAX_MARKDOWN_LENGTH = 5_000_000;
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

export function MarkdownEditor({ value, onChange, rows, className, placeholder, ariaLabel, disabled = false }: {
  value: string;
  onChange: (value: string) => void;
  rows: number;
  className: string;
  placeholder: string;
  ariaLabel: string;
  disabled?: boolean;
}) {
  const { t } = useLanguage();
  const input = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const [error, setError] = useState("");

  function insertImage(dataUrl: string) {
    const textarea = editor.current;
    if (!textarea) return;
    const currentValue = textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const prefix = start > 0 && currentValue[start - 1] !== "\n" ? "\n" : "";
    const suffix = end < currentValue.length && currentValue[end] !== "\n" ? "\n" : "";
    const markdown = `![${t("粘贴的图片")}](${dataUrl})`;
    const next = `${currentValue.slice(0, start)}${prefix}${markdown}${suffix}${currentValue.slice(end)}`;
    if (next.length > MAX_MARKDOWN_LENGTH) {
      setError(t("文字和图片内容总长度不能超过 500 万字符。"));
      return;
    }
    onChange(next);
    requestAnimationFrame(() => {
      const cursor = start + prefix.length + markdown.length;
      textarea.focus();
      textarea.setSelectionRange(cursor, cursor);
    });
  }

  function readImage(file: File) {
    if (!IMAGE_TYPES.has(file.type)) {
      setError(t("支持 PNG、JPEG、WebP 或 GIF 图片。"));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError(t("单张图片不能超过 1 MB。"));
      return;
    }
    setError("");
    const reader = new FileReader();
    reader.addEventListener("error", () => setError(t("无法读取图片，请重试。")), { once: true });
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") insertImage(reader.result);
    }, { once: true });
    reader.readAsDataURL(file);
  }

  function pasteImage(event: ClipboardEvent<HTMLTextAreaElement>) {
    const file = Array.from(event.clipboardData.items).find((item) => item.kind === "file" && item.type.startsWith("image/"))?.getAsFile();
    if (!file) return;
    event.preventDefault();
    readImage(file);
  }

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) readImage(file);
    event.target.value = "";
  }

  return <div className="markdown-editor">
    <div className="markdown-editor-toolbar"><span className="muted">{t("可直接粘贴图片 · 单张最大 1 MB")}</span><button type="button" className="icon-button" title={t("插入图片")} aria-label={t("插入图片")} disabled={disabled} onClick={() => input.current?.click()}><ImagePlus size={16} /></button><input ref={input} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={chooseImage} disabled={disabled} /></div>
    <textarea ref={editor} className={className} rows={rows} value={value} onChange={(event) => onChange(event.target.value)} onPaste={pasteImage} placeholder={placeholder} aria-label={ariaLabel} disabled={disabled} spellCheck={false} />
    {error && <ErrorNotice message={error} />}
  </div>;
}
