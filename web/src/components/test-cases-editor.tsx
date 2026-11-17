"use client";

import { useLanguage } from "@/lib/i18n";

import { Check, Code2, Plus, Save, Trash2 } from "lucide-react";
import { TestCase } from "@/lib/api";
import { ErrorNotice } from "./ui";

type Props = {
  cases: TestCase[];
  onChange: (cases: TestCase[]) => void;
  onSave: () => void;
  onDiscard: () => void;
  isDirty: boolean;
  isSaving: boolean;
  disabled: boolean;
  error: string;
};

export function TestCasesEditor({ cases, onChange, onSave, onDiscard, isDirty, isSaving, disabled, error }: Props) {
  const { t } = useLanguage();
  const isBusy = disabled || isSaving;
  const enabledCount = cases.filter((test) => test.enabled).length;

  function addCase(code = "", name = t("用例 {0}", cases.length + 1)) {
    onChange([...cases, { id: crypto.randomUUID(), name, code, enabled: true }]);
  }

  function changeCase(id: string, changes: Partial<TestCase>) {
    onChange(cases.map((test) => test.id === id ? { ...test, ...changes } : test));
  }

  return <section className="custom-tests-editor" aria-label={t("自定义测试用例")}>
    <div className="tests-editor-heading"><div><h2>{t("测试用例")}</h2><p className={isDirty ? "tests-unsaved" : "muted"}>{isDirty ? t("有未保存修改 · 运行时会自动保存") : <><Check size={12} />{t("已保存 ·")} {enabledCount} {t("个启用 /")} {cases.length} {t("个用例")}</>}</p></div>
      <button className="button button-small button-primary" disabled={isBusy || !isDirty} onClick={onSave}><Save size={14} />{isSaving ? t("保存中…") : t("保存用例")}</button></div>
    <div className="tests-help">{t("在测试代码中直接调用右侧定义的函数或类，用")} <code>assert</code> {t("检查结果。每条用例都会重新执行右侧代码，彼此不共享变量。没有启用的用例时，只运行代码并显示输出。")}</div>
    <details className="test-example"><summary>{t("测试代码怎么写？")}</summary><p>{t("假设右侧定义了")} <code>add(a, b)</code>：</p><pre>{t("assert add(1, 2) == 3\nassert add(-1, 1) == 0\nprint('加法测试通过')")}</pre><p>{t("PyTorch 可以使用")} <code>torch.testing.assert_close(actual, expected)</code> {t("检查张量。")}</p></details>
    <ErrorNotice message={error} />
    {!cases.length && <div className="tests-empty"><Code2 size={26} /><p>{t("还没有测试用例")}</p><span className="muted">{t("你仍然可以点击右上角“运行代码”查看输出。")}</span></div>}
    {cases.map((test, index) => <div className={`custom-test-card ${test.enabled ? "" : "test-disabled"}`} key={test.id}>
      <div className="custom-test-heading"><span className="test-number">{index + 1}</span><input aria-label={t("用例名称 {0}", index + 1)} className="field" value={test.name} maxLength={100} disabled={isBusy} placeholder={t("用例名称")} onChange={(event) => changeCase(test.id, { name: event.target.value })} />
        <label className="test-enabled"><input type="checkbox" aria-label={t("启用用例 {0}", index + 1)} checked={test.enabled} disabled={isBusy} onChange={(event) => changeCase(test.id, { enabled: event.target.checked })} />{t("启用")}</label>
        <button className="icon-button danger" disabled={isBusy} aria-label={t("删除用例 {0}", index + 1)} onClick={() => onChange(cases.filter((item) => item.id !== test.id))}><Trash2 size={15} /></button></div>
      <textarea aria-label={t("测试代码 {0}", index + 1)} className="field code-input custom-test-code" rows={6} maxLength={100000} value={test.code} disabled={isBusy} spellCheck={false} placeholder={t("# 直接调用右侧代码中的函数\nassert add(1, 2) == 3")} onChange={(event) => changeCase(test.id, { code: event.target.value })} />
    </div>)}
    <div className="tests-editor-actions"><button className="button button-small" disabled={isBusy || cases.length >= 50} onClick={() => addCase()}><Plus size={15} />{t("添加用例")}</button><button className="text-button" disabled={isBusy || cases.length >= 50} onClick={() => addCase(t("assert add(1, 2) == 3\nassert add(-1, 1) == 0\nprint('加法测试通过')"), t("示例：加法"))}>{t("添加加法示例")}</button>{isDirty && <button className="text-button tests-discard" disabled={isBusy} onClick={onDiscard}>{t("撤销未保存修改")}</button>}</div>
  </section>;
}
