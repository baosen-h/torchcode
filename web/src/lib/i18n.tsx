"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { ENGLISH } from "./translations";

export type Locale = "zh-CN" | "en";
type Value = string | number | undefined | null;
type Translator = (message: string, ...values: Value[]) => string;
const STORAGE_KEY = "torchcode_language";
const listeners = new Set<() => void>();
let preference: Locale | undefined;

function browserLocale(): Locale {
  if (preference) return preference;
  if (typeof window === "undefined") return "zh-CN";
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh-CN") return saved;
  } catch { /* Keep language switching available without browser storage. */ }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  function onStorage(event: StorageEvent) {
    if (event.key === STORAGE_KEY) { preference = undefined; listener(); }
  }
  window.addEventListener("storage", onStorage);
  return () => { listeners.delete(listener); window.removeEventListener("storage", onStorage); };
}

function setLocale(locale: Locale) {
  preference = locale;
  try { localStorage.setItem(STORAGE_KEY, locale); } catch { /* The current session still remembers it. */ }
  for (const listener of listeners) listener();
}

function interpolate(message: string, values: Value[]) {
  return message.replace(/\{(\d+)\}/g, (placeholder, index) => index in values ? String(values[index] ?? "") : placeholder);
}

function patternFor(message: string) {
  const indices: number[] = [];
  const pattern = message.split(/(\{\d+\})/).map((part) => {
    const match = part.match(/^\{(\d+)\}$/);
    if (match) { indices.push(Number(match[1])); return "([\\s\\S]*?)"; }
    return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("");
  return { regex: new RegExp(`^${pattern}$`), indices };
}

const reverse = new Map(Object.entries(ENGLISH).map(([chinese, english]) => [english, chinese]));
const templates = Object.entries(ENGLISH).filter(([key]) => /\{\d+\}/.test(key) && key !== "{0}：{1}").map(([chinese, english]) => ({
  chinese, english, source: patternFor(chinese), target: patternFor(english),
}));

export function translateFor(locale: Locale, message: string, ...values: Value[]): string {
  if (!message) return message;
  if (message.startsWith("Value error, ")) return translateFor(locale, message.slice(13));
  const exact = locale === "en" ? ENGLISH[message] : reverse.get(message);
  if (exact !== undefined) return interpolate(exact, values);
  if (values.length || locale === "zh-CN" && Object.hasOwn(ENGLISH, message)) return interpolate(message, values);
  if (message.includes("\n")) return message.split("\n").map((line) => translateFor(locale, line)).join("\n");
  for (const entry of templates) {
    const source = locale === "en" ? entry.source : entry.target;
    const match = message.match(source.regex);
    if (!match) continue;
    const captures: string[] = [];
    source.indices.forEach((index, position) => { captures[index] = match[position + 1]; });
    return interpolate(locale === "en" ? entry.english : entry.chinese, captures);
  }
  return message;
}

export function translate(message: string, ...values: Value[]) {
  return translateFor(browserLocale(), message, ...values);
}

const DEFAULT_CATEGORY_NAMES = new Set(["基础算子", "损失函数", "归一化与正则化", "模型结构", "优化与训练", "推理与分词", "训练调试"]);

type LanguageContextValue = { categoryLabel: (name: string) => string; locale: Locale; setLocale: (locale: Locale) => void; t: Translator };
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(subscribe, browserLocale, () => "zh-CN" as Locale);
  const t = useCallback<Translator>((message, ...values) => translateFor(locale, message, ...values), [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = locale === "en" ? "TorchCode · ML Code Practice" : "TorchCode · 机器学习代码练习";
  }, [locale]);
  const categoryLabel = useCallback((name: string) => locale === "en" && DEFAULT_CATEGORY_NAMES.has(name) ? t(name) : name, [locale, t]);
  const value = useMemo(() => ({ locale, setLocale, t, categoryLabel }), [locale, t, categoryLabel]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("LanguageProvider is required");
  return value;
}
