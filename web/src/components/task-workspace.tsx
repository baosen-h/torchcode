"use client";

import { useLanguage } from "@/lib/i18n";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Editor, { loader, OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { Allotment } from "allotment";
import { ArrowLeft, Check, ChevronDown, ExternalLink, FolderTree, Pencil, Play, RotateCcw, Trash2 } from "lucide-react";
import "allotment/dist/style.css";
import "katex/dist/katex.min.css";
import { api, COMPLETION_LABELS, errorMessage, safeReturnPath, STATUS_LABELS, TaskDetails, TaskStatus, TestCase } from "@/lib/api";
import { useTaskDraft } from "@/lib/use-task-draft";
import { useTestCases } from "@/lib/use-test-cases";
import { useLibrary } from "./library-provider";
import { CategoryPicker, DifficultyBadge, ErrorNotice, Modal } from "./ui";
import { TaskForm } from "./task-form";
import { SubmissionResponse, TestResults } from "./test-results";
import { TestCasesEditor } from "./test-cases-editor";
import { EnvironmentPicker } from "./environment-picker";
import { MarkdownEditor } from "./markdown-editor";
import { MarkdownContent as Markdown } from "./markdown-content";

loader.config({ paths: { vs: "/editor-assets/vs" } });

export function TaskWorkspace({ taskId }: { taskId: string }) {
  const { t } = useLanguage();
  const { database_id, error: libraryError, refresh } = useLibrary();
  const [task, setTask] = useState<TaskDetails | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!database_id) return;
    const controller = new AbortController();
    api<TaskDetails>(`/tasks/${encodeURIComponent(taskId)}`, { signal: controller.signal })
      .then((task) => { setTask(task); setError(""); })
      .catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [database_id, taskId, retry]);

  if (!task) return <div className="workspace-loading"><ErrorNotice message={error || libraryError} onRetry={() => { setRetry((value) => value + 1); void refresh().catch(() => undefined); }} />{!error && !libraryError && <p className="muted">{t("正在加载问题…")}</p>}<Link className="text-button" href="/problems"><ArrowLeft size={15} />{t("返回题库")}</Link></div>;
  return <LoadedWorkspace task={task} onTaskChange={setTask} />;
}

function LoadedWorkspace({ task, onTaskChange }: { task: TaskDetails; onTaskChange: (task: TaskDetails) => void }) {
  const { t, locale, categoryLabel } = useLanguage();
  const { categories, refresh } = useLibrary();
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnPath = safeReturnPath(searchParams.get("returnTo"));
  const { draft, updateDraft, flush, saveState, saveError, storageWarning } = useTaskDraft(task);
  const [activeTab, setActiveTab] = useState<"problem" | "notes" | "tests" | "results">("problem");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [results, setResults] = useState<SubmissionResponse | null>(null);
  const [error, setError] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingCategories, setIsEditingCategories] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState(task.category_ids);
  const [confirmation, setConfirmation] = useState<"delete" | "reset" | null>(null);
  const [notesPreview, setNotesPreview] = useState(false);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const isCustom = task.source === "custom";
  const testSuite = useTestCases(task, (updated) => {
    onTaskChange(updated);
    void refresh().catch(() => undefined);
  });
  const enabledTestCount = testSuite.cases.filter((test) => test.enabled).length;
  const hasSolved = task.progress.status === "solved";
  const saveLabels = { saved: t("已保存到数据库"), pending: t("待保存…"), saving: t("正在保存…"), error: t("保存失败 · 点击重试") };
  const handleEditorMount: OnMount = (instance) => { editorRef.current = instance; };

  async function returnToLibrary() {
    setIsBusy(true);
    setError("");
    try { await flush(); await refresh(); router.push(returnPath, { scroll: false }); }
    catch (error) { setError(errorMessage(error)); setIsBusy(false); }
  }

  async function updateStatus(status: TaskStatus) {
    setIsBusy(true);
    setError("");
    try {
      const progress = await api<TaskDetails["progress"]>(`/tasks/${task.id}/progress`, { method: "PATCH", body: JSON.stringify({ status }) });
      onTaskChange({ ...task, progress });
      void refresh().catch(() => undefined);
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  async function runTests() {
    setIsSubmitting(true);
    setResults(null);
    setError("");
    setActiveTab("results");
    try {
      await flush();
      let submissionTask = task;
      if (isCustom) {
        try { submissionTask = await testSuite.save(); }
        catch { setActiveTab("tests"); return; }
      }
      const result = await api<SubmissionResponse>(`/submit/${task.id}`, {
        method: "POST", body: JSON.stringify({ code: draft.code, ...(isCustom ? { tests_revision: submissionTask.tests_revision } : {}) }),
      });
      setResults(result);
      if (result.progress) onTaskChange({ ...submissionTask, progress: { ...submissionTask.progress, ...result.progress } });
      void refresh().catch(() => undefined);
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsSubmitting(false); }
  }

  function changeTestCases(cases: TestCase[]) {
    testSuite.change(cases);
    setResults(null);
  }

  async function saveCategories() {
    setIsBusy(true);
    setError("");
    try {
      await api(`/tasks/${task.id}/categories`, { method: "PUT", body: JSON.stringify({ category_ids: selectedCategories }) });
      onTaskChange({ ...task, category_ids: selectedCategories });
      setIsEditingCategories(false);
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  async function deleteTask() {
    setIsBusy(true);
    setError("");
    try {
      await flush();
      await api(`/tasks/${task.id}`, { method: "DELETE" });
      try { localStorage.removeItem(`torchcode_draft_${task.id}`); localStorage.removeItem(`torchcode_code_${task.id}`); localStorage.removeItem(`torchcode_tests_${task.id}`); } catch { /* The task has been deleted from the database. */ }
      await refresh();
      router.push(returnPath);
    } catch (error) { setError(errorMessage(error)); setIsBusy(false); }
  }

  return <main className="workspace">
    <div className="workspace-toolbar"><div className="workspace-breadcrumb"><button className="text-button" disabled={isBusy || isSubmitting} onClick={() => void returnToLibrary()}><ArrowLeft size={16} />{t("返回题库")}</button><span className="toolbar-divider" /><span className="truncate">{task.title}</span></div>
      <div className="toolbar-actions"><button className="button button-small" disabled={isBusy || isSubmitting} onClick={() => { setError(""); setConfirmation("reset"); }}><RotateCcw size={15} />{t("重置代码")}</button>
        {isCustom && <button className={`button ${hasSolved ? "button-solved" : ""}`} disabled={isBusy || isSubmitting || testSuite.isSaving} onClick={() => void updateStatus(hasSolved ? "todo" : "solved")}><Check size={16} />{hasSolved ? t("已解决 · 撤销") : t("标记已解决")}</button>}
        <button className="button button-run" disabled={isSubmitting || isBusy || testSuite.isSaving} onClick={() => void runTests()}><Play size={16} />{isSubmitting ? t("运行中…") : isCustom && !enabledTestCount ? t("运行代码") : t("运行测试")}</button></div>
    </div>
    <ErrorNotice message={error || saveError || storageWarning} onRetry={saveError ? () => void flush().catch(() => undefined) : undefined} />
    <div className="workspace-panes"><Allotment defaultSizes={[100, 100]} minSize={280} onChange={() => editorRef.current?.layout()}>
      <div className="workspace-left"><div className="workspace-tabs"><button className={activeTab === "problem" ? "active" : ""} onClick={() => setActiveTab("problem")}>{t("问题描述")}</button><button className={activeTab === "notes" ? "active" : ""} onClick={() => setActiveTab("notes")}>{t("我的解法")}</button>{isCustom && <button className={activeTab === "tests" ? "active" : ""} onClick={() => setActiveTab("tests")}>{t("测试用例")}{testSuite.isDirty && <span className="tests-unsaved" aria-hidden="true" title={t("有未保存的用例")}>●</span>}</button>}<button className={activeTab === "results" ? "active" : ""} onClick={() => setActiveTab("results")}>{t("测试结果")}{results && results.mode !== "run" && <span className={results.success ? "text-success" : "text-error"}>{results.passed}/{results.total}</span>}</button></div>
        <div className={`workspace-description ${activeTab === "notes" ? "notes-pane" : ""}`}>
          {activeTab === "problem" && <>
            <div className="task-title-row"><h1><span className="task-number">#{String(task.problem_number).padStart(2, "0")}</span>{task.title}</h1><div>{isCustom && <button className="icon-button" aria-label={t("编辑问题")} title={t("编辑问题")} disabled={isBusy} onClick={() => setIsEditing(true)}><Pencil size={17} /></button>}{isCustom && <button className="icon-button danger" aria-label={t("删除问题")} title={t("删除问题")} disabled={isBusy} onClick={() => { setError(""); setConfirmation("delete"); }}><Trash2 size={17} /></button>}</div></div>
            <div className="task-metadata"><DifficultyBadge difficulty={task.difficulty} /><span className={`source-label ${isCustom ? "custom" : ""}`}>{isCustom ? t("自建问题") : t("内置练习")}</span>{hasSolved && <span className="solved-label"><Check size={16} />{t("已解决 ·")} {task.progress.completion_source ? t(COMPLETION_LABELS[task.progress.completion_source]) : t("自行确认")}</span>}
              {isCustom && !hasSolved && <select className="status-select" aria-label={t("问题状态")} value={task.progress.status} disabled={isBusy} onChange={(event) => void updateStatus(event.target.value as TaskStatus)}><option value="todo">{t("未开始")}</option><option value="attempted">{t("进行中")}</option></select>}</div>
            <div className="task-categories">{categories.filter((category) => task.category_ids.includes(category.id)).map((category) => <span className="tag" key={category.id}>{categoryLabel(category.name)}</span>)}<button className="text-button" onClick={() => { setSelectedCategories(task.category_ids); setError(""); setIsEditingCategories(true); }}><FolderTree size={14} />{t("调整分类")}</button></div>
            {task.source_url && <a className="source-link" href={task.source_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} />{t("查看问题来源")}</a>}
            {task.description ? <Markdown preserveHeading={isCustom}>{task.description}</Markdown> : <p className="muted">{t("还没有问题描述，点击编辑补充背景和细节。")}</p>}
            {task.hint && <details className="task-hint"><summary><ChevronDown size={16} />{t("提示")}</summary><Markdown>{task.hint}</Markdown></details>}
            {isCustom && <div className="personal-task-note">{enabledTestCount ? t("已启用 {0} 个自定义用例。点击“运行测试”检查代码，全部通过后自动标记完成。", enabledTestCount) : <>{t("可以直接运行右侧代码查看输出，或在")}<button className="text-button" onClick={() => setActiveTab("tests")}>{t("测试用例")}</button>{t("中添加断言来验证结果。")}</>}{t("你也可以手动标记“已解决”。")}</div>}
            {task.progress.solved_at && <p className="solved-date">{t("解决于 {0}", new Date(task.progress.solved_at).toLocaleString(locale))}</p>}
            {task.progress.last_opened_at && <p className="solved-date">{t("最近打开：{0}", new Date(task.progress.last_opened_at).toLocaleString(locale))}</p>}
          </>}
          {activeTab === "notes" && <><div className="notes-heading"><div><h2>{t("我的解法")}</h2><p className="muted">{t("记录思路、关键代码与踩过的坑，支持 Markdown。")}</p></div><button className="button button-small" onClick={() => setNotesPreview(!notesPreview)}>{notesPreview ? t("继续编辑") : t("预览")}</button></div>{notesPreview ? draft.notes ? <Markdown>{draft.notes}</Markdown> : <div className="empty-state">{t("还没有解法记录。")}</div> : <MarkdownEditor className="notes-editor" rows={12} ariaLabel={t("我的解法")} value={draft.notes} onChange={(notes) => updateDraft({ notes })} placeholder={t("## 解决思路\n\n这次问题的原因是什么？\n\n## 关键实现\n\n## 下次遇到时要注意")} disabled={isBusy} />}</>}
          {activeTab === "results" && <TestResults results={results} isSubmitting={isSubmitting} />}
          {activeTab === "tests" && isCustom && <TestCasesEditor cases={testSuite.cases} onChange={changeTestCases} onSave={() => void testSuite.save().catch(() => undefined)} onDiscard={() => { testSuite.discard(); setResults(null); }} isDirty={testSuite.isDirty} isSaving={testSuite.isSaving} disabled={isBusy || isSubmitting} error={testSuite.error} />}
        </div>
      </div>
      <div className="workspace-right"><div className="editor-heading"><span><span className="editor-language-dot" />Python · {isCustom ? t("个人代码草稿") : "PyTorch"}</span><EnvironmentPicker /><button className={`save-indicator ${saveState === "error" ? "text-error" : ""}`} onClick={() => void flush().catch(() => undefined)} disabled={saveState === "saving"}>{saveLabels[saveState]}</button></div>
        <div className="editor-container"><Editor height="100%" language="python" theme="vs-dark" value={draft.code} onMount={handleEditorMount} onChange={(value) => { if ((value ?? "") !== draft.code) updateDraft({ code: value ?? "" }); }} loading={<div className="muted">{t("正在加载代码编辑器…")}</div>} options={{ readOnly: isSubmitting, automaticLayout: true, minimap: { enabled: false }, fontSize: 14, fontFamily: "'JetBrains Mono', 'Consolas', monospace", lineHeight: 24, padding: { top: 16 }, scrollBeyondLastLine: false, smoothScrolling: true, cursorBlinking: "smooth", cursorSmoothCaretAnimation: "on", wordWrap: "on", formatOnPaste: true }} /></div>
        <div className="editor-footer"><span>{t(STATUS_LABELS[task.progress.status])}</span><span>{isCustom ? t("代码与解法自动保存 · 用例需保存") : t("代码与解法自动保存")}</span></div>
      </div>
    </Allotment></div>
    {isEditing && <TaskForm task={task} onClose={() => setIsEditing(false)} onSaved={(updated) => { onTaskChange(updated); setIsEditing(false); }} />}
    {isEditingCategories && <Modal title={t("调整题目分类")} onClose={() => setIsEditingCategories(false)} isBusy={isBusy}><p className="muted modal-intro">{t("一道题可以属于多个分类；取消全部选择后进入“未分类”。")}</p><CategoryPicker selected={selectedCategories} onChange={setSelectedCategories} /><ErrorNotice message={error} /><div className="modal-actions"><button className="button" onClick={() => setIsEditingCategories(false)} disabled={isBusy}>{t("取消")}</button><button className="button button-primary" disabled={isBusy} onClick={() => void saveCategories()}>{isBusy ? t("保存中…") : t("保存分类")}</button></div></Modal>}
    {confirmation && <Modal title={confirmation === "delete" ? t("删除这个问题？") : t("重置代码？")} onClose={() => setConfirmation(null)} isBusy={isBusy}><p className="muted">{confirmation === "delete" ? t("“{0}”及其个人解法、代码草稿和完成记录将被删除。建议先在题库页导出备份。", task.title) : t("当前代码草稿将恢复为题目的初始代码。个人解法和完成状态保留。")}</p><ErrorNotice message={error} /><div className="modal-actions"><button className="button" onClick={() => setConfirmation(null)} disabled={isBusy}>{t("取消")}</button><button className={`button ${confirmation === "delete" ? "button-danger" : "button-primary"}`} disabled={isBusy} onClick={() => { if (confirmation === "delete") { void deleteTask(); return; } updateDraft({ code: task.initial_code }); setResults(null); setConfirmation(null); }}>{isBusy ? t("处理中…") : confirmation === "delete" ? t("确认删除") : t("重置代码")}</button></div></Modal>}
  </main>;
}
