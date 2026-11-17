"use client";

import { useLanguage } from "@/lib/i18n";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDownToLine, ArrowUpFromLine, Check, Circle, Clock3, FolderTree, Plus, Search, X } from "lucide-react";
import { api, COMPLETION_LABELS, errorMessage, STATUS_LABELS, Task, TaskDetails } from "@/lib/api";
import { useLibrary } from "./library-provider";
import { DifficultyBadge, ErrorNotice, Modal } from "./ui";
import { TaskForm } from "./task-form";

const SCROLL_KEY = "torchcode_library_scroll";
const MAX_BACKUP_SIZE = 20 * 1024 * 1024;

export function ProblemLibrary() {
  const { t, categoryLabel } = useLanguage();
  const { tasks, categories, isLoading, error: libraryError, refresh } = useLibrary();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState("");
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [backup, setBackup] = useState<unknown>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const scrollContainer = useRef<HTMLElement>(null);
  const didRestoreScroll = useRef(false);
  const query = searchParams.get("q") || "";
  const categoryId = searchParams.get("category") || "";
  const source = searchParams.get("source") || "";
  const difficulty = searchParams.get("difficulty") || "";
  const status = searchParams.get("status") || "";
  const sort = searchParams.get("sort") || "default";
  const returnPath = `/problems${searchParams.size ? `?${searchParams.toString()}` : ""}`;

  useEffect(() => {
    if (isLoading || didRestoreScroll.current) return;
    didRestoreScroll.current = true;
    try {
      const saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
      if (saved?.path === returnPath && scrollContainer.current) scrollContainer.current.scrollTop = saved.top;
    } catch { /* The library works when browser storage is unavailable. */ }
  }, [isLoading, returnPath]);

  function filter(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (value) next.set(key, value);
    if (!value) next.delete(key);
    window.history.replaceState(null, "", `/problems${next.size ? `?${next}` : ""}`);
  }

  function rememberPosition() {
    try { sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ path: returnPath, top: scrollContainer.current?.scrollTop || 0 })); }
    catch { /* Scroll restoration is optional. */ }
  }

  async function toggleSolved(task: Task) {
    setBusyId(task.id);
    setError("");
    try {
      await api(`/tasks/${task.id}/progress`, { method: "PATCH", body: JSON.stringify({ status: task.progress.status === "solved" ? "todo" : "solved" }) });
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusyId(""); }
  }

  async function exportBackup() {
    setIsBackingUp(true);
    setError("");
    try {
      const data = await api("/library/backup");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `torchcode-backup-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(t("备份已导出，包含自建问题、分类、完成状态、个人解法和代码草稿。"));
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBackingUp(false); }
  }

  async function selectBackup(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    try {
      if (file.size > MAX_BACKUP_SIZE) throw new Error(t("备份文件不能超过 20 MB。"));
      const data = JSON.parse(await file.text());
      if (data?.version !== 1 || !Array.isArray(data.custom_tasks) || !Array.isArray(data.categories)) throw new Error(t("请选择有效的 TorchCode 备份文件。"));
      setBackup(data);
    } catch (error) { setError(errorMessage(error)); }
  }

  async function restoreBackup() {
    setIsRestoring(true);
    setError("");
    try {
      const result = await api<{ tasks: number; categories: number; progress: number }>("/library/restore", { method: "POST", body: JSON.stringify(backup) });
      const restored = backup as { task_ids: string[] };
      try {
        for (const taskId of restored.task_ids) {
          localStorage.removeItem(`torchcode_draft_${taskId}`);
          localStorage.removeItem(`torchcode_code_${taskId}`);
          localStorage.removeItem(`torchcode_tests_${taskId}`);
        }
      } catch { /* Imported database records are already durable. */ }
      setBackup(null);
      await refresh();
      setMessage(t("导入完成：{0} 个自建问题、{1} 个分类、{2} 条学习记录。", result.tasks, result.categories, result.progress));
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsRestoring(false); }
  }

  function openCreatedTask(task: TaskDetails) {
    setIsCreating(false);
    rememberPosition();
    router.push(`/problems/${task.id}?returnTo=${encodeURIComponent(returnPath)}`);
  }

  const filteredTasks = tasks.filter((task) => {
    const matchesCategory = !categoryId || (categoryId === "uncategorized" ? !task.category_ids.length : task.category_ids.includes(categoryId));
    const matchesQuery = `${task.title}\n${task.search_text}`.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim());
    return matchesCategory && matchesQuery && (!source || task.source === source)
      && (!difficulty || (difficulty === "unset" ? !task.difficulty : task.difficulty === difficulty))
      && (!status || task.progress.status === status);
  }).sort((first, second) => {
    if (sort === "title") return first.title.localeCompare(second.title);
    if (sort === "recent") return (second.progress.updated_at || second.updated_at || "").localeCompare(first.progress.updated_at || first.updated_at || "");
    if (first.source !== second.source) return first.source === "custom" ? -1 : 1;
    if (first.source === "custom") return second.created_at.localeCompare(first.created_at);
    return ({ "": 3, Easy: 0, Medium: 1, Hard: 2 }[first.difficulty] - { "": 3, Easy: 0, Medium: 1, Hard: 2 }[second.difficulty]) || first.title.localeCompare(second.title);
  });
  const solvedCount = tasks.filter((task) => task.progress.status === "solved").length;
  const attemptedCount = tasks.filter((task) => task.progress.status === "attempted").length;
  const customCount = tasks.filter((task) => task.source === "custom").length;
  const selectedCategory = categories.find((category) => category.id === categoryId)?.name;

  return <main className="library-scroll" ref={scrollContainer}>
    <div className="library-content">
      <div className="page-heading"><div><p className="eyebrow">YOUR PROBLEM LIBRARY</p><h1>{t("把解决过的问题，变成积累。")}</h1><p className="muted">{t("练习内置题目，也记录项目中遇到的每一个问题。")}</p></div>
        <button className="button button-primary" disabled={isLoading || !!libraryError} onClick={() => setIsCreating(true)}><Plus size={18} />{t("新增问题")}</button></div>
      <div className="library-summary"><span><strong>{tasks.length}</strong>{t("全部问题")}</span><span className="text-success"><strong>{solvedCount}</strong>{t("已解决")}</span><span><strong>{attemptedCount}</strong>{t("进行中")}</span><span><strong>{customCount}</strong>{t("自建问题")}</span><div className="summary-progress" role="progressbar" aria-label={t("已解决比例")} aria-valuenow={solvedCount} aria-valuemin={0} aria-valuemax={tasks.length || 1}><div style={{ width: `${tasks.length ? solvedCount / tasks.length * 100 : 0}%` }} /></div></div>
      <ErrorNotice message={error || libraryError} onRetry={() => void refresh().catch(() => undefined)} />
      {message && <div className="success-notice" role="status"><Check size={16} />{t(message)}<button className="icon-button" aria-label={t("关闭提示")} onClick={() => setMessage("")}><X size={15} /></button></div>}
      <div className="library-grid">
        <aside className="category-sidebar"><div className="sidebar-heading"><span>{t("主题分类")}</span><Link href="/categories" aria-label={t("管理分类")}><FolderTree size={16} /></Link></div>
          <button className={`category-link ${!categoryId ? "active" : ""}`} onClick={() => filter("category", "")}><span>{t("全部问题")}</span><span>{tasks.length}</span></button>
          {categories.map((category) => {
            const categorized = tasks.filter((task) => task.category_ids.includes(category.id));
            return <button key={category.id} className={`category-link ${categoryId === category.id ? "active" : ""}`} onClick={() => filter("category", category.id)}><span>{categoryLabel(category.name)}</span><span>{categorized.filter((task) => task.progress.status === "solved").length}/{categorized.length}</span></button>;
          })}
          <button className={`category-link ${categoryId === "uncategorized" ? "active" : ""}`} onClick={() => filter("category", "uncategorized")}><span>{t("未分类")}</span><span>{tasks.filter((task) => !task.category_ids.length).length}</span></button>
          <div className="sidebar-note">{t("分类支持多选。可以在分类管理中改名、排序或合并。")}</div>
        </aside>
        <section className="problem-panel" aria-label={t("题目列表")}>
          <div className="source-tabs">{[{ value: "", label: t("全部题目"), count: tasks.length }, { value: "builtin", label: t("内置练习"), count: tasks.length - customCount }, { value: "custom", label: t("我的问题"), count: customCount }].map((tab) => <button key={tab.value} className={source === tab.value ? "active" : ""} onClick={() => filter("source", tab.value)}>{tab.label}<span>{tab.count}</span></button>)}</div>
          <div className="filter-bar"><label className="search-field"><Search size={17} /><input aria-label={t("搜索问题")} placeholder={t("搜索标题、问题描述或个人解法…")} value={query} onChange={(event) => filter("q", event.target.value)} /></label>
            <select className="field filter-select" aria-label={t("按状态筛选")} value={status} onChange={(event) => filter("status", event.target.value)}><option value="">{t("全部状态")}</option><option value="todo">{t("未开始")}</option><option value="attempted">{t("进行中")}</option><option value="solved">{t("已解决")}</option></select>
            <select className="field filter-select" aria-label={t("按难度筛选")} value={difficulty} onChange={(event) => filter("difficulty", event.target.value)}><option value="">{t("全部难度")}</option><option>Easy</option><option>Medium</option><option>Hard</option><option value="unset">{t("未设置")}</option></select>
          </div>
          <div className="list-caption"><span>{(selectedCategory ? categoryLabel(selectedCategory) : "") || (categoryId === "uncategorized" ? t("未分类") : t("全部分类"))}<span className="muted">{t("· {0} 个问题", filteredTasks.length)}</span></span><select aria-label={t("题目排序")} className="sort-select" value={sort} onChange={(event) => filter("sort", event.target.value)}><option value="default">{t("默认排序")}</option><option value="recent">{t("最近更新")}</option><option value="title">{t("标题排序")}</option></select></div>
          {isLoading ? <div className="empty-state">{t("正在加载题库…")}</div> : <div className="table-scroll"><table className="problem-table"><thead><tr><th className="status-column">{t("状态")}</th><th>{t("题目")}</th><th>{t("分类")}</th><th>{t("难度")}</th><th>{t("来源")}</th></tr></thead><tbody>
            {filteredTasks.map((task) => <tr key={task.id}>
              <td className="status-column">{task.source === "custom" ? <button className={`status-button status-${task.progress.status}`} aria-label={t("{0}：{1}", task.progress.status === "solved" ? t("撤销完成") : t("标记已解决"), task.title)} disabled={!!busyId} onClick={() => void toggleSolved(task)}>{task.progress.status === "solved" ? <Check size={19} /> : task.progress.status === "attempted" ? <Clock3 size={17} /> : <Circle size={17} />}</button> : <span className={`status-button status-${task.progress.status}`} title={t(STATUS_LABELS[task.progress.status])} aria-label={t(STATUS_LABELS[task.progress.status])}>{task.progress.status === "solved" ? <Check size={19} /> : task.progress.status === "attempted" ? <Clock3 size={17} /> : <Circle size={17} />}</span>}</td>
              <td className="problem-title-cell"><Link href={`/problems/${task.id}?returnTo=${encodeURIComponent(returnPath)}`} onClick={rememberPosition} className={`problem-title ${task.progress.status === "solved" ? "solved" : ""}`}>{task.title}</Link>
                {task.progress.completion_source && <div className="completion-note">{t(COMPLETION_LABELS[task.progress.completion_source])}</div>}</td>
              <td><div className="table-categories">{task.category_ids.length ? categories.filter((category) => task.category_ids.includes(category.id)).map((category) => <button key={category.id} className="tag" onClick={() => filter("category", category.id)}>{categoryLabel(category.name)}</button>) : <span className="muted">—</span>}</div></td>
              <td><DifficultyBadge difficulty={task.difficulty} /></td><td><span className={`source-label ${task.source === "custom" ? "custom" : ""}`}>{task.source === "custom" ? t("自建") : t("内置")}</span></td>
            </tr>)}
          </tbody></table>{!filteredTasks.length && <div className="empty-state"><Search size={30} /><h3>{tasks.length ? t("没有找到匹配的问题") : t("从第一个问题开始")}</h3><p>{tasks.length ? t("试试其他关键词，或清除筛选条件。") : t("点击右上角新增问题，记录你的学习与实践。")}</p>{!!searchParams.size && <button className="button" onClick={() => window.history.replaceState(null, "", "/problems")}>{t("清除筛选")}</button>}</div>}</div>}
          <div className="library-footer"><span className="muted">{t("完成的问题会划线显示，仍可点击查看解法。")}</span><div><button className="text-button" disabled={isBackingUp || !tasks.length} onClick={() => void exportBackup()}><ArrowDownToLine size={15} />{isBackingUp ? t("导出中…") : t("导出备份")}</button><button className="text-button" onClick={() => fileInput.current?.click()}><ArrowUpFromLine size={15} />{t("导入备份")}</button><input ref={fileInput} type="file" accept="application/json,.json" className="visually-hidden" aria-label={t("选择备份文件")} onChange={(event) => void selectBackup(event)} /></div></div>
        </section>
      </div>
    </div>
    {isCreating && <TaskForm onClose={() => setIsCreating(false)} onSaved={openCreatedTask} />}
    {backup !== null && <Modal title={t("导入备份")} onClose={() => setBackup(null)} isBusy={isRestoring}><p className="muted">{t("备份会合并到当前题库。相同 ID 的问题、分类关联和学习记录会使用备份中的内容更新，其他问题保留。建议先导出当前备份。")}</p><ErrorNotice message={error} /><div className="modal-actions"><button className="button" disabled={isRestoring} onClick={() => setBackup(null)}>{t("取消")}</button><button className="button button-primary" disabled={isRestoring} onClick={() => void restoreBackup()}>{isRestoring ? t("导入中…") : t("确认导入")}</button></div></Modal>}
  </main>;
}
