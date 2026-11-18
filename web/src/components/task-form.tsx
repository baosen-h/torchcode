"use client";

import { useLanguage } from "@/lib/i18n";

import { FormEvent, useState } from "react";
import { Plus } from "lucide-react";
import { api, Category, Difficulty, errorMessage, TaskDetails, TaskInput } from "@/lib/api";
import { useLibrary } from "./library-provider";
import { CategoryPicker, ErrorNotice, Modal } from "./ui";
import { MarkdownEditor } from "./markdown-editor";

export function TaskForm({ task, onClose, onSaved }: { task?: TaskDetails; onClose: () => void; onSaved: (task: TaskDetails) => void }) {
  const { t } = useLanguage();
  const { refresh } = useLibrary();
  const [values, setValues] = useState<TaskInput>({
    title: task?.title || "", description: task?.description || "", difficulty: task?.difficulty || "",
    initial_code: task?.initial_code || "", source_url: task?.source_url || "", category_ids: task?.category_ids || [],
  });
  const [categoryName, setCategoryName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingCategory, setIsAddingCategory] = useState(false);
  const [error, setError] = useState("");
  const isBusy = isSaving || isAddingCategory;

  function change<K extends keyof TaskInput>(key: K, value: TaskInput[K]) {
    setValues((previous) => ({ ...previous, [key]: value }));
  }

  async function addCategory() {
    if (!categoryName.trim()) return;
    setIsAddingCategory(true);
    setError("");
    try {
      const category = await api<Category>("/categories", { method: "POST", body: JSON.stringify({ name: categoryName }) });
      await refresh();
      setValues((previous) => ({ ...previous, category_ids: [...previous.category_ids, category.id] }));
      setCategoryName("");
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsAddingCategory(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (isBusy) return;
    setIsSaving(true);
    setError("");
    try {
      const saved = await api<TaskDetails>(task ? `/tasks/${task.id}` : "/tasks", {
        method: task ? "PUT" : "POST", body: JSON.stringify(values),
      });
      await refresh();
      onSaved(saved);
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsSaving(false); }
  }

  return <Modal title={task ? t("编辑问题") : t("新增问题")} onClose={onClose} isBusy={isBusy} wide>
    <p className="muted modal-intro">{t("记录你想解决的问题。无需官方答案，解决后可以自行标记完成。")}</p>
    <form onSubmit={save} className="form-stack">
      <fieldset disabled={isBusy} className="form-stack">
        <label className="form-label">{t("问题标题")} <span className="required">*</span><input className="field" required maxLength={200} value={values.title} onChange={(event) => change("title", event.target.value)} placeholder={t("例如：排查混合精度训练中的 NaN")} autoFocus /></label>
        <div className="form-label">{t("问题描述")} <span className="muted">{t("支持 Markdown 和公式")}</span><MarkdownEditor className="field" rows={8} value={values.description} onChange={(value) => change("description", value)} placeholder={t("描述背景、遇到的问题、约束或示例……")} ariaLabel={t("问题描述")} disabled={isBusy} /></div>
        <div className="form-label">{t("分类")} <span className="muted">{t("可多选")}</span><CategoryPicker selected={values.category_ids} onChange={(ids) => change("category_ids", ids)} />
          <div className="inline-form"><input aria-label={t("新分类名称")} className="field" maxLength={60} value={categoryName} onChange={(event) => setCategoryName(event.target.value)} placeholder={t("新增一个分类")} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void addCategory(); } }} /><button type="button" className="button" disabled={!categoryName.trim()} onClick={() => void addCategory()}><Plus size={15} />{t("添加")}</button></div>
        </div>
        <div className="form-columns"><label className="form-label">{t("难度")}<select className="field" value={values.difficulty} onChange={(event) => change("difficulty", event.target.value as Difficulty)}><option value="">{t("不设难度")}</option><option>Easy</option><option>Medium</option><option>Hard</option></select></label>
          <label className="form-label">{t("来源链接")} <span className="muted">{t("可选")}</span><input className="field" type="url" value={values.source_url} onChange={(event) => change("source_url", event.target.value)} placeholder="https://" /></label></div>
        <label className="form-label">{t("初始代码")} <span className="muted">{t("可选；与个人代码草稿分别保存")}</span><textarea className="field code-input" rows={4} value={values.initial_code} onChange={(event) => change("initial_code", event.target.value)} spellCheck={false} placeholder={t("# 可以先留空")} /></label>
      </fieldset>
      <ErrorNotice message={error} />
      <div className="modal-actions"><button type="button" className="button" onClick={onClose} disabled={isBusy}>{t("取消")}</button><button className="button button-primary" disabled={isBusy}>{isSaving ? t("保存中…") : task ? t("保存修改") : t("创建问题")}</button></div>
    </form>
  </Modal>;
}
