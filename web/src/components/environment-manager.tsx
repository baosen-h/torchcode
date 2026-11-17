"use client";

import { useLanguage } from "@/lib/i18n";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Check, Download, FolderPlus, RefreshCw, Terminal } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { environmentReturnPath, PythonEnvironment, RuntimeState } from "@/lib/runtime";
import { ErrorNotice } from "./ui";

const PYTHON_VERSIONS = ["3.11", "3.10", "3.12", "3.13"];

export function EnvironmentManager() {
  const { t } = useLanguage();
  const parameters = useSearchParams();
  const [state, setState] = useState<RuntimeState | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [name, setName] = useState("");
  const [version, setVersion] = useState("3.11");
  const [target, setTarget] = useState("");
  const [packages, setPackages] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const isFetching = useRef(false);
  const isMounted = useRef(false);
  const hasRunningJob = state?.job?.status === "running";
  const isDisabled = isBusy || isLoading || hasRunningJob;
  const packageTargets = state?.environments.filter((environment) => environment.can_install && environment.has_python) || [];

  const load = useCallback(async (refresh = false) => {
    if (isFetching.current) return;
    isFetching.current = true;
    const current = ++generation.current;
    try {
      const next = await api<RuntimeState>(`/environments${refresh ? "?refresh=true" : ""}`);
      if (!isMounted.current || current !== generation.current) return;
      setState(next);
      setError("");
    } catch (error) {
      if (isMounted.current && current === generation.current) setError(errorMessage(error));
    } finally {
      isFetching.current = false;
      if (isMounted.current && current === generation.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => { isMounted.current = true; void load(); return () => { isMounted.current = false; }; }, [load]);
  useEffect(() => {
    if (!hasRunningJob) return;
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [hasRunningJob, load]);

  async function perform(path: string, body: object, method = "POST") {
    setIsBusy(true);
    setError("");
    setMessage("");
    try {
      await api(path, { method, body: JSON.stringify(body) });
      if (method === "PUT") setMessage(t("运行环境已切换，对下一次运行生效。"));
      await load();
    } catch (error) { setError(errorMessage(error)); }
    finally { setIsBusy(false); }
  }

  function selectEnvironment(environment: PythonEnvironment) {
    void perform("/environments/current", { environment_id: environment.id }, "PUT");
  }

  return <main className="library-scroll"><div className="library-content environment-content">
    <div className="page-heading"><div><p className="eyebrow">PYTHON RUNTIME</p><h1>{t("运行环境")}</h1><p className="muted">{t("为内置练习与自建问题选择 Python，在网页中创建环境和安装依赖。")}</p></div>
      <Link className="button" href={environmentReturnPath(parameters.get("returnTo"))}><ArrowLeft size={15} />{parameters.get("returnTo") ? t("返回题目") : t("返回题库")}</Link></div>
    <div className="runtime-current"><Terminal size={20} /><div><span className="muted">{t("当前运行环境")}</span><strong>{(state?.selected.name ? t(state.selected.name) : "") || t("正在读取…")}</strong><code>{state?.selected.python}</code></div><span className="runtime-scope">{t("对下一次运行生效 · 自动记住选择")}</span></div>
    <ErrorNotice message={error || state?.error || ""} onRetry={() => void load(true)} />
    {state?.discovery_error && <div className="execution-warning">{t(state.discovery_error)}</div>}
    {message && <div className="success-notice" role="status"><Check size={16} />{t(message)}</div>}
    <div className="environment-grid"><section className="environment-panel"><div className="environment-section-heading"><div><h2>{t("已有环境")}</h2><p className="muted">{t("默认环境显示实际解释器；空环境需先安装 Python。")}</p></div><button className="button button-small" disabled={isDisabled} onClick={() => { setIsLoading(true); void load(true); }}><RefreshCw size={14} />{t("刷新")}</button></div>
      {isLoading && !state && <p className="muted" role="status">{t("正在检测本机 Conda 环境…")}</p>}
      <div className="environment-list">{state?.environments.map((environment) => <article className={`environment-card ${state.selected.id === environment.id ? "selected" : ""}`} key={environment.id}>
        <div className="environment-card-heading"><h3>{t(environment.name)}</h3>{state.selected.id === environment.id && <span className="runtime-active"><Check size={13} />{t("当前使用")}</span>}{!environment.has_python && <span className="runtime-missing">{t("未安装 Python")}</span>}</div>
        <code>{environment.has_python ? environment.python : environment.prefix}</code>
        {environment.is_backend && <p className="muted">{t("正在承载网页后端，保留原有依赖。")}</p>}
        <div className="environment-card-actions"><button className="button button-small" aria-label={t("使用环境 {0}", environment.name)} disabled={isDisabled || !environment.has_python || state.selected.id === environment.id} onClick={() => selectEnvironment(environment)}>{t("使用此环境")}</button>
          {!environment.has_python && environment.can_install && <button className="button button-small button-primary" aria-label={t("安装 Python 到 {0}", environment.name)} disabled={isDisabled || !state.conda_available} onClick={() => void perform("/environments/python", { environment_id: environment.id, python_version: version })}><Download size={14} />{t("安装 Python")} {version}</button>}</div>
      </article>)}</div>
    </section><div className="environment-forms"><section className="environment-panel"><div className="environment-section-heading"><div><h2><FolderPlus size={17} />{t("新建 Conda 环境")}</h2><p className="muted">{t("安装独立的 Python 和 pip；运行内置题还需安装 torch。")}</p></div></div>
      <form className="form-stack" onSubmit={(event) => { event.preventDefault(); void perform("/environments", { name: name.trim(), python_version: version }); }}><label className="form-label">{t("环境名称")}<input className="field" value={name} maxLength={40} required placeholder={t("例如 torchcode-study")} disabled={isDisabled || !state?.conda_available} onChange={(event) => setName(event.target.value)} /></label>
        <label className="form-label">{t("Python 版本")}<select className="field" value={version} disabled={isDisabled || !state?.conda_available} onChange={(event) => setVersion(event.target.value)}>{PYTHON_VERSIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
        <button className="button button-primary" disabled={isDisabled || !state?.conda_available || !name.trim()}><FolderPlus size={15} />{t("创建并安装")}</button></form>
    </section><section className="environment-panel"><div className="environment-section-heading"><div><h2><Download size={17} />{t("安装 Python 依赖")}</h2><p className="muted">{t("安装到指定环境。每行一个包名，可指定版本。")}</p></div></div>
      <form className="form-stack" onSubmit={(event) => { event.preventDefault(); void perform("/environments/packages", { environment_id: target || packageTargets[0]?.id, packages: packages.trim().split(/\s+/).filter(Boolean) }); }}>
        <label className="form-label">{t("安装到环境")}<select className="field" value={target || packageTargets[0]?.id || ""} disabled={isDisabled || !packageTargets.length} onChange={(event) => setTarget(event.target.value)}>{!packageTargets.length && <option value="">{t("请先创建或安装独立 Python 环境")}</option>}{packageTargets.map((environment) => <option key={environment.id} value={environment.id}>{t(environment.name)}</option>)}</select></label>
        <label className="form-label">{t("依赖包")}<textarea className="field code-input" rows={4} value={packages} disabled={isDisabled || !packageTargets.length} onChange={(event) => setPackages(event.target.value)} placeholder={"numpy\npandas==2.2.3\ntorch"} required maxLength={6000} /></label>
        <p className="muted runtime-form-note">{t("PyTorch 的 CUDA 专用安装命令请在终端执行；此处使用当前 pip 源。安装完成后不会自动切换环境。")}</p>
        <button className="button" disabled={isDisabled || !packageTargets.length || !packages.trim()}><Download size={15} />{t("安装依赖")}</button></form>
    </section></div></div>
    {state?.job && <section className="environment-panel environment-job" aria-label={t("环境安装日志")}><div className="environment-section-heading"><div><h2>{t(state.job.title)}</h2><p className={state.job.status === "failed" ? "text-error" : "muted"} role="status">{state.job.status === "running" ? t("安装中，日志每 2 秒更新。可以离开本页，稍后回来查看。") : t(state.job.message)}</p></div><span className={state.job.status === "succeeded" ? "text-success" : state.job.status === "failed" ? "text-error" : "runtime-missing"}>{({ running: t("正在安装"), succeeded: t("安装成功"), failed: t("安装失败") })[state.job.status]}</span></div><pre tabIndex={0}>{state.job.log || t("正在准备安装…")}</pre></section>}
    <p className="muted environment-footer-note">{t("环境选择保存在本机，适用于所有题目。安装期间暂停运行代码；代码运行期间不能安装。创建和安装需要联网，服务需保持开启。此处仅从本机访问，不提供删除环境功能。")}</p>
  </div></main>;
}
