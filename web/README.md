# TorchCode 机器学习代码题库

在网页中练习机器学习代码、管理自己的问题和解法，自建题可使用纯 Python、NumPy、scikit-learn、PyTorch 等已安装依赖。原有 41 道 PyTorch 内置练习与自动判题保留。

[English overview and setup](../README.md) · [中文介绍](../README.zh-CN.md)

## 题目编号、时间和图片

内置题按上游目录顺序编号，自建题在数据库中分配递增编号；删除题目不会复用编号。首次打开题目会更新“最近打开”，查看题目列表本身不会改变它。旧数据库启动时会为已有自建题补号，保留原题目、完成记录和解法。

问题描述和个人解法支持 Markdown。可将 PNG、JPEG、WebP、GIF 图片直接粘贴到编辑区，或点图片按钮选择文件；单张图片最大 10 MB，随题目保存在 SQLite，并包含在 JSON 备份中。图片单独保存在 SQLite 的 images 表，正文只保存简短的 /api/images/… 路径，导出备份包含图片。已有 data URL 图片会在升级或编辑时转换，图片内容保留。

## 中英文切换

顶部语言菜单可切换中文 / English。首次访问跟随浏览器语言（中文浏览器显示中文，其他语言显示英文）；手动选择后通过 `torchcode_language` 记住偏好，同源标签页自动同步。浏览器禁用本地存储时，当前页面仍可切换。切换不重置已填写的表单或草稿。

默认分类仅翻译显示名称，不修改数据库；自定义分类、题目内容、笔记、代码、程序输出和安装工具日志保留原文。中英文 README 分别使用 `assets/screenshots/zh-CN/` 和 `assets/screenshots/en/` 的截图。

## 一键启动（Windows）

双击仓库根目录的 `start_torchcode.bat`。启动器默认通过 Conda 的 `torchcode` 环境启动后端，启动前端并打开浏览器。首次使用需已有 Node.js、Conda、前后端依赖；缺少依赖时启动窗口会显示原因及日志位置。

启动器会显示后端实际使用的 Python 路径，并将首次验证可用的后端解释器记在 `data/startup-backend.json`，后续启动保持使用该解释器，避免网页中安装 Python 后影响后端启动。需要重选后端解释器时可删除这个配置文件，再启动。空 Conda 环境可能通过 PATH 使用系统 Python；可以在“运行环境”页为该空环境安装独立 Python。启动后端的 Python 与网页选中的题目执行环境相互独立。

保持启动窗口开启，按回车停止本次启动的进程。已在运行且健康检查属于本项目的服务会复用，退出时不会关闭复用的服务；端口被其他应用占用时会提示，不会结束其他进程。

默认前端端口 3000、后端端口 8000。也可以在终端执行：

```powershell
.\start_torchcode.bat -BackendPort 8001 -FrontendPort 3001
.\start_torchcode.bat -CheckOnly
```

启动日志在 `data/startup-logs/`。找不到 Conda 时，从 Anaconda Prompt 启动，或将 `TORCHCODE_CONDA_EXE` 设置为 `conda.exe` 的完整路径。后端启动环境可通过 `TORCHCODE_BACKEND_ENV` 修改，默认是 `torchcode`。

## 网页运行环境

- 顶部“运行环境”入口或题目编辑器上方的环境入口可以打开 `/environments`。
- 列出本机 Conda 环境及其真实 Python 路径。空环境明确显示“未安装 Python”，不能误用系统 Python 执行题目。
- 点击“使用此环境”后，内置题和自建题的下一次运行会使用所选环境，选择自动保存。已有运行继续使用启动时的环境。选择失效时提示重新选择，不静默切换。
- “新建 Conda 环境”会安装所选 Python 版本及 pip。也可为现有空环境安装 Python，版本使用表单中当前选择的版本。
- “安装 Python 依赖”支持每行一个包名或版本条件，例如 `numpy`、`pandas==2.2.3`。通过目标环境的 Python 调用 pip；后端环境和 base 不提供安装入口。
- 安装是后台任务，页面显示日志和成功／失败状态，可以离开页面后回来查看。一次只运行一个安装任务，安装期间暂停执行题目；有代码运行时不能开始安装。
- 创建和安装需要联网，单个命令最多等待 30 分钟。服务关闭会中断安装，失败时环境可能部分更新，请根据日志处理。不会自动删除或重建任何环境。
- 依赖安装使用现有 pip 源，不接受终端命令、安装选项、网址或本地文件。PyTorch CUDA 特定版本请按官方安装方式在终端配置，之后回到网页选择环境。
- 环境管理仅支持本机访问。选择保存在数据库同目录的 `*.runtime.json`，安装日志保存在 `environment-logs/`。题库 JSON 备份不包含解释器、依赖或本机环境路径。此功能面向本机个人使用。

## 启动

后端终端（在仓库根目录）：

```powershell
conda activate torchcode
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

前端终端：

```powershell
cd web
npm install
npm run dev
```

打开 `http://localhost:3000`，首页会进入 `/problems`。
已有依赖时无需重复执行 `npm install`。后端依赖见 `api/requirements.txt`，已有环境可直接启动。

生产构建：`npm run build`，然后 `npm start`。

前端通过同源 `/api` 转发到 `http://127.0.0.1:8000`。
如果后端在其他地址，启动或构建前设置 `TORCHCODE_API_URL`（不含 `/api` 后缀）。
只有需要直接跨域调用 API 时才设置 `NEXT_PUBLIC_API_BASE_URL`（包含 `/api` 后缀）。

## 使用

- **题库 `/problems`**：搜索标题、描述及个人解法；按分类、难度、完成状态、内置或自建筛选。筛选保存在 URL，返回时恢复列表位置。
- **新增问题**：标题必填，描述支持 Markdown 和公式，难度、来源链接、初始代码均可选；分类支持多选和即时新增。
- **题目详情 `/problems/题目ID`**：内置题运行测试后自动完成。自建问题可以直接运行代码，也可以编写测试；启用的用例全部通过后自动完成，并保留手动标记、撤销功能。已解决的问题在题库中划线显示。
- **自定义测试**：自建问题的“测试用例”标签页支持添加、命名、启停、编辑和删除用例，最多 50 条。测试脚本可以直接调用右侧代码的函数、类及导入的模块，用 `assert` 或 `torch.testing.assert_close` 验证结果。每条用例重新执行右侧代码，互不共享用户变量。用例可以手动保存，点击运行时也会自动保存；未保存的编辑会缓存在当前浏览器。
- **运行结果**：没有启用的用例时显示代码输出、标准错误或异常，不将“运行成功”当成测试通过。配置了用例时逐条显示通过／失败、耗时、测试代码、输出及错误堆栈。修改已通过的用例后，需要重新测试；手动确认的完成状态保留。
- **我的解法**：记录分析、关键实现及结论，支持 Markdown 预览。代码草稿和解法自动保存，编辑器顶部显示保存状态。
- **编辑器资源**：Monaco 从本地依赖提供，不再依赖外部 CDN。需要保留安装后的 `web/node_modules/monaco-editor`。
- **分类管理 `/categories`**：新增、重命名、上下移动、合并和删除。删除分类保留题目，无其他分类的题目进入“未分类”。内置题也可以调整分类。
- **备份**：题库列表底部可以导出或导入 JSON，包含自建题、分类、分类关联、完成状态、个人解法和代码草稿。导入为合并更新，同 ID 的记录使用备份中的内容更新，其他记录保留。

自定义用例和启停状态也包含在备份中，旧版 JSON 备份仍然可以导入。数据库在后端启动时自动添加所需字段，保留已有问题和解法。

例如右侧实现了 `add(a, b)`，测试代码可以写：

```python
assert add(1, 2) == 3
assert add(-1, 1) == 0
print("加法测试通过")
```

题目代码在所选 Python 环境中以独立进程执行；默认使用后端 Python。单次运行默认超时为 30 秒，启动后端前可设置 `TORCHCODE_RUN_TIMEOUT`（1–120 秒）。

## 数据位置与迁移

数据库默认位于仓库的 `data/library.db`，与内置题目代码分开。
可通过后端环境变量 `TORCHCODE_DB_PATH` 指定其他数据库文件。

首次访问新版网页时，会自动读取**当前浏览器、当前网址来源**中旧版的 `torchcode_solved_tasks` 和 `torchcode_code_*`，导入数据库。迁移按数据库标识记录，原浏览器数据不删除，已有数据库记录不会被旧数据覆盖。

编辑过程中还会保留浏览器本地草稿，临时断开后端时可以在下次打开问题后恢复并继续同步。
跨浏览器或设备共用同一个后端会看到同一份数据库；这是个人单用户题库，没有引入账号体系。

备份优先使用网页导出。需要直接复制 SQLite 数据库时，先停止后端，避免遗漏正在写入 WAL 的数据。
现有 `torch_judge/progress.py` 的 Notebook 进度文件仍独立保留；网页旧数据迁移针对浏览器中的记录。

原有根目录 Docker 配置仍启动 JupyterLab；网页前端和 FastAPI 按上面的命令启动。

## 检查

```powershell
conda activate torchcode
# 需要测试依赖时：python -m pip install -r api/requirements-dev.txt
python -m unittest discover -s api/tests -v
cd web
npm run lint
npm run build
```

启动器会比较后台实际加载的代码指纹，自动替换本项目的旧后台。界面检测到不兼容的旧后台时会给出明确提示，不再显示 undefined 题号。时间单独显示在“最近打开”列中，来源直接显示网址。
