"use client";

import { useLanguage } from "@/lib/i18n";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowLeft, ArrowUp, Check, FolderTree, Merge, Pencil, Plus, Trash2 } from "lucide-react";
import { api, Category, errorMessage } from "@/lib/api";
import { useLibrary } from "./library-provider";
import { ErrorNotice, Modal } from "./ui";

type CategoryAction = { type: "rename" | "merge" | "delete"; category: Category };

export function CategoryManager() {
  const { t, categoryLabel } = useLanguage();
  const { categories, tasks, isLoading, error: libraryError, refresh } = useLibrary();
  const [newName, setNewName] = useState("");
  const [action, setAction] = useState<CategoryAction | null>(null);
  const [name, setName] = useState("");
  const [targetId, setTargetId] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function createCategory(event: FormEvent) {
    event.preventDefault();
    setIsBusy(true);
    setError("");
    try {
      await api("/categories", { method: "POST", body: JSON.stringify({ name: newName }) });
      setNewName("");
      await refresh();
      setMessage(t("分类已添加，可以在新增问题或题目详情中选择。"));
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  async function moveCategory(index: number, offset: number) {
    const next = [...categories];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    setIsBusy(true);
    setError("");
    try {
      await api("/categories/order", { method: "PUT", body: JSON.stringify({ category_ids: next.map((category) => category.id) }) });
      await refresh();
      setMessage(t("分类顺序已更新。"));
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  function openAction(type: CategoryAction["type"], category: Category) {
    setName(category.name);
    setTargetId(categories.find((item) => item.id !== category.id)?.id || "");
    setError("");
    setAction({ type, category });
  }

  async function applyAction(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    setIsBusy(true);
    setError("");
    try {
      const path = `/categories/${action.category.id}`;
      if (action.type === "rename") await api(path, { method: "PUT", body: JSON.stringify({ name }) });
      if (action.type === "delete") await api(path, { method: "DELETE" });
      if (action.type === "merge") await api(`${path}/merge`, { method: "POST", body: JSON.stringify({ target_id: targetId }) });
      setAction(null);
      await refresh();
      setMessage(action.type === "delete" ? t("分类已删除，其中的问题全部保留。") : action.type === "merge" ? t("分类已合并，题目关联已迁移。") : t("分类名称已更新，题目关联已保留。"));
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  const actionTitle = action ? { rename: t("重命名分类"), merge: t("合并分类"), delete: t("删除分类") }[action.type] : "";

  return <main className="library-scroll"><div className="category-content">
    <Link className="text-button back-link" href="/problems"><ArrowLeft size={16} />{t("返回题库")}</Link>
    <div className="page-heading"><div><p className="eyebrow">ORGANIZE YOUR KNOWLEDGE</p><h1>{t("分类管理")}</h1><p className="muted">{t("按自己的思路组织问题。改名、排序和合并，题目始终保留。")}</p></div><FolderTree className="heading-icon" size={38} /></div>
    <ErrorNotice message={error || libraryError} onRetry={() => void refresh().catch(() => undefined)} />
    {message && <div className="success-notice" role="status"><Check size={16} />{t(message)}</div>}
    <section className="category-management-panel"><form className="category-create-form" onSubmit={(event) => void createCategory(event)}><label htmlFor="category-name" className="form-label">{t("新增分类")}</label><div className="inline-form"><input id="category-name" className="field" value={newName} maxLength={60} required placeholder={t("例如：分布式训练、项目排错")} disabled={isBusy} onChange={(event) => setNewName(event.target.value)} /><button className="button button-primary" disabled={isBusy || !newName.trim() || isLoading || !!libraryError}><Plus size={17} />{t("添加分类")}</button></div></form>
      <div className="category-table-heading"><span>{t("{0} 个分类", categories.length)}</span><span>{t("顺序会同步到题库与分类选择器")}</span></div>
      {isLoading && <div className="empty-state">{t("正在加载分类…")}</div>}
      {categories.map((category, index) => {
        const count = tasks.filter((task) => task.category_ids.includes(category.id)).length;
        return <div className="category-management-row" key={category.id}><div className="category-order"><button className="icon-button" disabled={isBusy || index === 0} aria-label={t("上移 {0}", categoryLabel(category.name))} onClick={() => void moveCategory(index, -1)}><ArrowUp size={15} /></button><button className="icon-button" disabled={isBusy || index === categories.length - 1} aria-label={t("下移 {0}", categoryLabel(category.name))} onClick={() => void moveCategory(index, 1)}><ArrowDown size={15} /></button></div>
          <div className="category-name"><Link href={`/problems?category=${category.id}`}>{categoryLabel(category.name)}</Link><span className="muted">{t("{0} 个问题", count)}</span></div>
          <div className="category-row-actions"><button className="text-button" disabled={isBusy} onClick={() => openAction("rename", category)}><Pencil size={14} />{t("改名")}</button><button className="text-button" disabled={isBusy || categories.length < 2} onClick={() => openAction("merge", category)}><Merge size={14} />{t("合并")}</button><button className="text-button danger" disabled={isBusy} onClick={() => openAction("delete", category)}><Trash2 size={14} />{t("删除")}</button></div>
        </div>;
      })}
      {!isLoading && !categories.length && <div className="empty-state"><FolderTree size={30} /><h3>{t("建立你的第一个分类")}</h3><p>{t("没有分类的问题仍然会保存在“未分类”中。")}</p></div>}
    </section>
    <p className="category-help">{t("一个问题可以归入多个分类。删除分类只移除分类关联；失去全部分类的问题会显示在“未分类”。")}</p>
    {action && <Modal title={actionTitle} onClose={() => setAction(null)} isBusy={isBusy}><form className="form-stack" onSubmit={(event) => void applyAction(event)}>
      {action.type === "rename" && <label className="form-label">{t("分类名称")}<input className="field" maxLength={60} required autoFocus value={name} disabled={isBusy} onChange={(event) => setName(event.target.value)} /></label>}
      {action.type === "merge" && <><p className="muted">{t("把“{0}”中的所有问题归入下方分类，然后移除原分类。题目和解法都会保留。", categoryLabel(action.category.name))}</p><label className="form-label">{t("合并到")}<select className="field" value={targetId} disabled={isBusy} onChange={(event) => setTargetId(event.target.value)}>{categories.filter((category) => category.id !== action.category.id).map((category) => <option value={category.id} key={category.id}>{categoryLabel(category.name)}</option>)}</select></label></>}
      {action.type === "delete" && <p className="muted">{t("确定删除“{0}”？其中的 {1} 个问题会保留；没有其他分类的问题将进入“未分类”。", categoryLabel(action.category.name), tasks.filter((task) => task.category_ids.includes(action.category.id)).length)}</p>}
      <ErrorNotice message={error} /><div className="modal-actions"><button type="button" className="button" disabled={isBusy} onClick={() => setAction(null)}>{t("取消")}</button><button className={`button ${action.type === "delete" ? "button-danger" : "button-primary"}`} disabled={isBusy || (action.type === "rename" && !name.trim())}>{isBusy ? t("处理中…") : action.type === "delete" ? t("删除分类") : action.type === "merge" ? t("确认合并") : t("保存名称")}</button></div>
    </form></Modal>}
  </div></main>;
}
