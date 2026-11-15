# AI 分析模块 · 细化设计规格 v2（基于已落地实现重评）

- 日期：2026-11-15
- 状态：设计评审稿 v2.4，**仍不产出实现代码**；实现级规格另见 `docs/AI_IMPLEMENTATION_SPEC.md`
- 前提：领导四项决策不变（① 正文+附件+人工上传 ② 内网本地、接口暂不通 ③ 复用 `analysis_content` ④ 转入分析时触发）；选编号 1「先补 §12 四个待定项，再评一次」
- 收编：R1 已解除、R4 已实测解除；2 个 commit `8a751d3` + `26561e6` **已 push** 到 `origin/optimization`，worktree 分支已同步，详见 §0.1 / §0.2
- 状态订正（v2.4）：Ollama 是**主机关机、预期停机**；会话模型 `hy4free` 无本地 OpenAI 兼容端点，详见 §10

---

## 0.1 收编状态更新 v2.3（2026-11-15，领导连续选「1 先收编」→「1 补齐配套」→「1 2 3」）

主工作目录 `/home/qianqianjie/tenders` / `optimization` 分支，**两个 commit，均已 push**：

| commit | 内容 | 规模 |
|---|---|---|
| `8a751d3` | 收编 6 个 AI 核心文件（§0 清单） | 6 files / 2917 insertions(+) |
| `26561e6` | 补齐 2 行蓝图注册 + PDF 解析依赖链 | 2 files / 10 insertions(+) |

| 核查项 | 结果 |
|---|---|
| 脱敏 | 6 文件无硬编码口令；`DB_PASSWORD` 走 `os.getenv`（`fetch_detail_content.py:93`、`extract_indicators.py:57`）；默认值仅 `127.0.0.1:11434/v1` 与 `qwen3.8:27b`；`.env` 由 `.gitignore:24` 排除，已跟踪的只有 `.env.example` |
| 提交范围控制 | 第 1 次用 pathspec 限定 6 个新文件；第 2 次用 `git hash-object -w --stdin` + `git update-index --cacheinfo` 从 HEAD 基线重建 blob，**只注入 2 行注册 + 8 行依赖**。暂存区原有的无关文档 `.trae/documents/user-management-overhaul.md` 先 `restore --staged` 退回未跟踪（文件未丢），两次均未混入 |
| 边界证据 | 提交后工作区 `__init__.py` diff 由 `71/15` 降为 `69/15`、`requirements.txt` 保持 `24/9` —— 正好只有那 10 行被 HEAD 吸收，其余安全加固与版本升级一行未带走 |
| 提交身份 | 沿用仓库 local `qianqianjie <qianqianjie@example.com>`，与历史 5 条一致（订正：本机**此仓库**已有 local 身份，无需 `-c` 兜底） |

**R4 依赖链依据**（`requirements.txt` 新增 4 行固定版本）：

| 包 | 版本 | 依据 |
|---|---|---|
| `pdfplumber` | 0.11.9 | 本机用户级已装、实测 `import pdfplumber` 成功；PyPI 最新 0.11.10 未实测 |
| `pdfminer.six` | 20251230 | pdfplumber 0.11.9 METADATA 精确锁定；**要求 Python ≥3.10** |
| `Pillow` | 12.2.0 | 部署 venv 已装实测版本 |
| `pypdfium2` | 5.6.0 | pdfplumber METADATA 要求 ≥4.18.0，取本机已装版本 |

部署 venv 实测 **Python 3.12.3**，满足 ≥3.10；**README 记载的 3.8/3.9 已过时**。
只补 pdfplumber 一行不够：`pyvenv.cfg` 为 `include-system-site-packages = false`，
venv 内 `pdfplumber` / `pdfminer` / `pypdfium2` 均为 NO，`PIL` 为 YES（12.2.0）。
**离线 wheel 已于 §0.2 备齐并实测安装。**

**push 已完成（v2.3）**：`git push origin optimization:optimization` 经显式密钥 SSH 成功，
`58ee9fd..26561e6`。`git ls-remote origin refs/heads/optimization` 复核远端 =
`26561e64a863...`，与本地 HEAD 一致，ahead 归零。推送范围严格为上表 8 files /
2927 insertions(+)；push 前再次复核脱敏（`git show` 敏感词 0 命中、`.env` 未跟踪）。

**分支已同步（v2.3）**：worktree 分支 `workbuddy/optimization-9f749643` 用
`git merge --ff-only 26561e6` 快进到 `26561e6`，6 个 AI 文件在会话工作区全部可见
（行数复核一致），蓝图注册 `__init__.py:116,130` 与 4 行依赖 `requirements.txt:42-45` 均已到位；
两个未跟踪项 `.workbuddy/` 与本文档未受影响，无 MERGE_HEAD 残留。

**仍未解决**：

1. 主工作目录仍剩 **32 个**未提交/修改项（含 69 行安全加固、Flask/Scrapy 版本升级、`.env.example` 口令置空等），需另行决定收编范围。
2. 本文档 `docs/AI_ANALYSIS_DESIGN_SPEC.md` 与 `.workbuddy/memory/` 在 worktree 中仍为 `??` 未跟踪，**远端没有这份规格**，换机器会丢。
3. Ollama 11434 仍挂（v2.3 复测 `/api/tags` 6s 超时），接口降级 G3 未实现。
4. `requirements.txt` 未锁 PDF 依赖的传递层版本，离线部署须用 §0.2 的 wheel 目录，不能裸跑 `pip install -r`。
5. `_doc_to_text` 用 `tempfile.TemporaryDirectory()` 且 profile 写死 `/tmp/lo_prof_*`（`fetch_detail_content.py:375-379`）；本机 `/tmp` 为 10MB tmpfs，大附件转换会失败。本轮未改代码。

**主动订正（影响 §G1 实现）**：规格 §4 G1 表格中「被 `__init__.py:144-149` CSRF 豁免」是基于
worktree 的 commit 版本；**主工作目录版本已删除 focus/main 的 CSRF 豁免**（含
`csrf.exempt(api_move_to_analysis)`），并把限流豁免重构为 `_rate_limit_exempt()`。
「转单接口补 `require_auth_write`」这条结论仍成立，但实现前须按主工作目录版本复核实际装饰器与豁免链。

---

## 0.2 R4 最后一公里 · 实测记录 v2.3（2026-11-15，领导选「1 2 3」）

**离线 wheel 已备**：`/home/qianqianjie/mountDisk/tenders_wheels/`（仓库外、大分区、22 MB），
用部署 venv 的 pip 下载 `--only-binary=:all:`，共 **8 个 wheel**：
4 个锁定包 + 自动解析出的传递依赖 `charset-normalizer 3.5.2` / `cryptography 50.0.2` /
`cffi 2.1.1` / `pycparser 3.12`。索引为清华镜像，全部 cp312 / manylinux 匹配本机。

**已装进部署 venv**：`pip install --no-index --find-links=<wheel目录> --no-deps` 装
`pdfplumber 0.11.9` / `pdfminer.six 20251230` / `pypdfium2 5.6.0`；
`Pillow 12.2.0` 原本已装、dry-run 显示「already satisfied」，未重装、未动其他包。
`pip list` 复核 4 个版本全部一致。

**PDF 解析实测通过**（生产函数，非单独 demo）：用 soffice 生成一页中文 PDF 样本
（`probe/sample.pdf`，36 KB，`%PDF-1.7`），在部署 venv 里 import
`tools/fetch_detail_content.py` 并跑三段：

| 用例 | 结果 |
|---|---|
| `_pdf_to_text(pdf_bytes)` | 提取 154 字，中文项目名 / 控制价 `210000` / 尾部英文行全部命中 |
| `_fetch_file_text()` 走 `%PDF` 分支 | 输出与直调完全一致（154 字），附件下载→判头→解析链路通 |
| 非 PDF 字节 | 返回 `''`，防御分支正常 |

**新发现（未改代码）**：wheel 目录的传递依赖版本与部署 venv 已装版本不一致
（`charset-normalizer 3.5.2 vs 3.4.4`、`cryptography 50.0.2 vs 46.0.5`、
`cffi 2.1.1 vs 2.0.0`、`pycparser 3.12 vs 3.0`）。当前部署以 `--no-deps` 补装、实测可跑；
但**全新离线环境用整套 wheel 会得到另一组版本组合，未实测**。
离线部署命令必须是：
`pip install --no-index --find-links=/home/qianqianjie/mountDisk/tenders_wheels -r requirements.txt`。

---

## 0. v1 作废声明（必须先读）

**v1 的大前提错了，本文件已整体重写。** 前几轮我只在 worktree `optimization-9f749643` 里检索，而 AI 分析模块的实现是主工作目录 `/home/qianqianjie/tenders/` 里 **6 个未提交（untracked）文件**，worktree 看不到。两个目录同为 commit `58ee9fd`，但工作区内容不同：

```
$ cd /home/qianqianjie/tenders && git status --short -- <6 个 AI 文件>
?? flask_web/app/routes/ai_analysis.py
?? flask_web/app/services/ai_analyzer_service.py
?? flask_web/templates/ai_analysis.html
?? sql_scripts_20260406/add_ai_analysis_fields_2026-11-11.sql
?? tools/extract_indicators.py
?? tools/fetch_detail_content.py
```

| v1 结论 | 核实结果 | v2 处置 |
|---|---|---|
| 「AI 分析 0 实现」 | **错**。已有一整套服务、路由、页面、迁移脚本 | 改为增量改造 |
| 「爬虫不抓正文、附件解析 0%」 | **错**。3 地区 adapter + PDF/DOC 解析已实现，库里已有 781 条正文 | 不再重建 |
| 「`.env.example` 无模型接口配置」 | **错**（表述不全）。部署 `.env` 已有 `AI_BASE_URL/AI_MODEL/AI_API_KEY/AI_TIMEOUT` | 复用现有 4 键 |
| 「需新建 3 张旁路表 + 独立 worker + 8 个配置键」 | **不必要**。现有 `ai_analysis JSON` / `detail_content MEDIUMTEXT` / `ai_analyzed_at` 已承担溯源与状态 | v1 §3、§5、§8 全部作废 |
| 「7 站点正文适配 30% + 附件解析 15%」 | **错**。已落地 | 工作量重算，见 §6 |
| 「11 张表」「mod_wsgi 2 进程（`__init__.py:61`）」 | 仍订正：`CREATE TABLE` 共 10 处；`:61` 是注释括注非配置，真实限流在 `:57` `2000/hour + 300/min`、`:60` `6000/min` | 保留订正 |

此前一直找不到的「AI 分析模块设计方案」，现在可以确认：它**已经以代码形式落地**，只是未纳入版本库，所以历史会话与 worktree 都检索不到。原项目根 md 只有 README / DEPLOYMENT / FRP_C75_INCIDENT / TESTING_AND_MONITORING / url_Source / 关键词特效修复总结，无独立方案文档。

---

## 1. 现有实现清单（实测）

| 文件 | 职责 | 关键证据 |
|---|---|---|
| `services/ai_analyzer_service.py` | Ollama OpenAI 兼容调用、基础指标抽取、关键词命中后的深入分析（对照我方资质）、批量线程任务、写库 | `:97-103` 配置、`:37-71` prompt、`:253-306` 调用与 JSON 解析、`:340-366` 深度 prompt、`:401-455` `company_profile`、`:564-592` 单条分析、`:596-618` 幂等加列、`:654-689` 保存、`:718-804` 批量线程 |
| `routes/ai_analysis.py` | `/ai-analysis` 页面与 8 个接口，全套 `@login_required` | `:38-69` 统计、`:72-195` 列表、`:239-263` 批量、`:272-296` 单条同步、`:299-327` 深入分析、`:330-346` 公司档案、`:349-383` 启动抓正文脚本 |
| `tools/fetch_detail_content.py` | 抓详情正文回写 `detail_content`；山东 API / 江苏 HTML / 浙江 PDF 三地区 adapter；PDF·DOC·XLS 附件解析 | `:257-346` 山东、`:354-389` pdfplumber + libreoffice、`:407-452` 附件链接与通用页、`:460-467` 按表分发、`:500-571` 并发与限速 |
| `tools/extract_indicators.py` | 规则抽取 7 项指标（不调 AI），AI 兜底 | 文件头 docstring |
| `sql_scripts_20260406/add_ai_analysis_fields_2026-11-11.sql` | 3 张表加 `detail_content MEDIUMTEXT` / `ai_analysis JSON` / `ai_analysis_status` / `ai_analyzed_at` + 索引 | `:58-60` |
| `templates/ai_analysis.html` | 745 行分析页面 | `wc -l` |
| 部署 `__init__.py` | 注册 `ai_analysis_bp` | `:143,157` |

**结论：领导决策 ① 的前两路、② 的内网本地模型，已经实现并跑过数据。**

---

## 2. 实测基线（本轮新验）

| 项 | 结果 | 来源 |
|---|---|---|
| 数据库 | MariaDB 10.11.14，`sql_mode=STRICT_TRANS_TABLES,...`，库 `bidding_db` | 只读连库 `SELECT VERSION(), @@sql_mode` |
| 4 列已落地 | `bidding_info` / `jiangsu_bidding_info` / `zhejiang_bidding_info` 均有 `detail_content mediumtext`、`ai_analysis longtext`、`ai_analysis_status varchar(20)`、`ai_analyzed_at datetime`；`analysis_projects.analysis_content` 仍为 `text` | `information_schema.columns` |
| 正文抓取进度 | 山东 406/975、江苏 194/194、浙江 181/481，合计 **781 条** | 三表 `COUNT` |
| AI 分析进度 | 三表各 20 条 `ok`，合计 **60 条**，`failed=0`；成功窗口 **2026-11-12 21:09:02 ~ 21:18:50** | `ai_analyzed_at` |
| 人工侧 | `analysis_projects` 158 条，其中 **75 条**有 `analysis_content` | `COUNT` |
| 模型配置 | `AI_BASE_URL=http://127.0.0.1:11434/v1`、`AI_MODEL=qwen3.8:27b`、`AI_TIMEOUT=180`、`AI_API_KEY` 为空 | 部署 `.env`（密钥值未读取展示） |
| 接口当前状态 | TCP 11434 **通**；`GET /api/tags`、`GET /v1/models` 均 6s 超时；`POST /v1/chat/completions` 20s 超时 | 本轮三次实测 |
| 版本库状态 | v2 撰写时为 6 个 `??` / 38 个变更；**现已收编并 push**：`8a751d3` + `26561e6` → `origin/optimization`（远端 = 本地 HEAD `26561e6`），worktree 分支已快进同步；主工作目录剩余 32 个变更（详见 §0.1 / §0.2） | `git ls-remote`、`git rev-parse HEAD` |
| 本机非生产 | 无 `apache` 用户/组、无 `/var/www/html`；工作区属主 root | `getent` / `ls` / `id` |

---

## 3. §12 四个待定项 · 核实结果（本轮任务）

| # | 待定项 | 结论 | 是否验成 |
|---|---|---|---|
| 1 | 接口契约（地址/鉴权/返回结构） | **契约已确定，POST 成功响应未验成**。请求 `POST {AI_BASE_URL}/chat/completions`，OpenAI 兼容：`model/messages/temperature=0.1/max_tokens/stream=false/think=false/response_format=json_object`，`Authorization: Bearer` 仅当 key 非空（`ai_analyzer_service.py:256-274`）；响应取 `choices[0].message.content`，为空时回退 `reasoning`（`:291-299`）；400 时逐项去掉 `response_format`、`think` 重试（`:281-289`）。**当前接口超时，无法实测成功响应**，只能按代码反推 | 部分 |
| 2 | `TEXT` 截断行为 | **实测完成，且需订正 v1**。严格模式下 65,535 B 通过、65,536 B 报 `1406 Data too long`；20,000 汉字（60,000 B）通过、22,000 汉字（66,000 B）报 1406。会话关掉严格模式后 70,000 B 被**静默截断**为 65,535 B。**生产当前是严格模式 ⇒ 超长是报错 1406（人工编辑接口会 500），不是静默截断**；两种都需写入前限长 | 是 |
| 3 | 7 站点详情页抓样 | **不再需要"抓样定方案"，实现已落地并有 781 条真实正文**。但覆盖率待核：现有按**表**分派 3 个 adapter（`fetch_detail_content.py:460-467`），山东 5 个 spider 共用 `fetch_shandong`，仅 `ccgp-shandong.gov.cn` 走 `getDetail` API，其余走通用页跟进（`:311-318`）。本机未抓公网样本 | 部分 |
| 4 | 生产 `apache` 附件目录写权限 | **本机无法验**（无该用户/目录）。但 v2 设计改为「上传后只存解析文本、不落盘原件」（见 §5 G2），**该待定项可直接消除**；若领导要求留存原件，再按非 Web 目录 + 带鉴权下载处理 | 否（已绕过） |

---

## 4. 与领导四项决策的差距矩阵

| 决策 | 现状 | 差距 | v2 改造 |
|---|---|---|---|
| ① 正文 + 附件 + 人工上传 | 正文 ✅ 附件 ✅ 人工上传 ❌ | 第三路完全没有；`routes/ai_analysis.py` 与模板 grep `request.files/upload` 0 命中 | G2 |
| ② 内网本地、接口暂不通 | Ollama 本地 ✅，配置 ✅；接口当前挂了 ✅ | 无健康检查，`failed=0` 掩盖故障；`AI_TIMEOUT=180` 对同步接口过长；任务状态在进程内存 | G3 |
| ③ 复用 `analysis_content` | ❌ **完全没打通**：AI 模块全文 grep `analysis_content` / `analysis_projects` 0 命中 | 两条链各存各的：AI 结果在公告表 `ai_analysis JSON`，人工结论在 `analysis_projects.analysis_content` | G1 |
| ④ 转入分析时触发 | ❌ 现为「当日发布 + 命中关键词」的批量任务与页面手动按钮（`routes/ai_analysis.py:257-259`） | 转单动作没有调用 AI | G1 |

---

## 5. 增量改造设计（三个缺口）

**总原则：复用现有列与配置，不重建。** 作废 v1 的 3 张旁路表、独立 worker、8 个新配置键。溯源能力现有已够：`detail_content` 存原文、`ai_analysis.model` 存模型（`:248`）、`ai_analyzed_at` 存时间、JSON 列可存多次结果。

### G1 · 转单打通两条链（决策 ③④）

| 项 | 规格 |
|---|---|
| 触发点 | `POST /focus/api/move-to-analysis`（worktree `focus.py:177`）保持不变 |
| 鉴权 | 该接口无 `@login_required` 且被 `__init__.py:144-149` CSRF 豁免 → 补 `require_auth_write`（`decorators.py:53-85`） |
| 动作 | INSERT `analysis_projects` 同一事务内，按 `detail_url` 反查 3 张公告表的 `ai_analysis`；若 `ai_analysis_status='ok'`，把 `budget→control_price`、`deadline→bid_open_date`、`purchaser→tenderer` 映射回填，并把 `summary/risk/compliance/scoring/qualification` 拼成结论写入 `analysis_content` |
| 限长 | 写入前按 **字节** 校验 < 65,535 B（建议上限 60,000 B / 约 20,000 汉字），避免 1406 |
| 不覆盖 | `analysis_content` 非空时不覆盖人工结论；接口不通或无结果时留空并标记待处理，**转单照常秒回** |
| 异步 | 转单只做一次查表与字段映射（毫秒级），**无需队列**；模型调用不在转单链路里 |

### G2 · 人工上传（决策 ① 第三路）

| 项 | 规格 |
|---|---|
| 接口 | 新增 `POST /ai-analysis/api/upload/<table>/<rid>`，沿用该蓝图全套 `@login_required` |
| 处理 | 复用 `fetch_detail_content.py:354-389` 的 `_pdf_to_text` / `_doc_to_text` 解析能力，解析后写 `detail_content`，`ai_analysis_status` 置 `pending` |
| 存储 | **一期只存解析文本、不落盘原件** → 无附件目录权限问题、无 `/static` 直出泄密风险（`__init__.py:46-47`） |
| 降级价值 | 接口不通期，这是唯一能让新公告进入 AI 链路的输入；也补齐领导第 ① 项 |

### G3 · 接口降级与可观测（决策 ②）

- 复用 `ai_analysis_status` 的 `pending/ok/failed` 三态，不再另建状态机；在 `ai_analysis.error` 里区分 `connect / timeout / bad_json / empty_content`。
- 增加轻量健康检查（`GET /api/tags`，2s 超时），页面显示「模型在线 / 超时」；**当前 `/api/tags` 6s 无响应，说明挂的是 Ollama 服务本身而非业务代码**。
- `_task_state` 为进程内字典 + daemon 线程（`ai_analyzer_service.py:693-705,803`），mod_wsgi 多进程下各存一份、重启即丢 → 长期应把批量任务改为独立进程；一期至少在 `/api/task` 返回里标注该局限。
- 单条同步分析接口（`routes/ai_analysis.py:272-296`）叠加 `AI_TIMEOUT=180` 会占死 worker → 单条接口超时单独降到 30s 或改后台任务。
- 配置：复用现有 4 键；如需开关，只新增 `AI_FILL_ON_MOVE`（默认 false）。v1 的 8 个键作废。

### 不变清单

7 个 spider 列表页解析、`items.py`、3 张公告表与 `analysis_projects` 的现有字段语义、现有装饰器实现、13 个蓝图注册、限流参数、人工编辑接口 `PUT /analysis/api/update/<id>`。

---

## 6. 工作量占比重算

| 阶段 | 内容 | v2 占比 | 对应 v1 |
|---|---|---|---|
| A | G1 转单打通 + 字段映射 + 限长 + 补鉴权 | 40% | v1 的 45% 队列/旁路大部分已不需要 |
| B | G2 人工上传 + 解析复用 | 25% | v1 的 15% 附件解析已实现 |
| C | G3 健康检查 / 降级 / 超时 / 任务状态 | 20% | — |
| D | 版本库收编 + 依赖补齐（见 R1/R4） | 15% | — |

v1 的「7 站点正文 30% + 附件 15%」归零：已落地。

---

## 7. 风险与长稳项（按优先级）

| # | 风险 | 证据 | 处置 |
|---|---|---|---|
| R1 | **已解除**：6 个核心文件 + 2 行蓝图注册入库并已 push 到 `origin/optimization`（v2.3 `git ls-remote` 复核）；仅剩其余 32 个变更与规格文档本身未收编 | `git ls-remote`、`git status --short` | 其余变更另行评估 |
| R2 | **性质订正**：Ollama 主机关机，属预期停机（非服务故障）；但停机 3 天 `failed=0` 无人发现这一**健康检查缺失**风险不变。最后成功 11-12 21:18，v2.4 复测 `/api/tags` 仍超时 | 领导确认 + 库统计 + 接口实测 | G3 健康检查 + `unavailable` 展示态 |
| R3 | `analysis_content TEXT` 严格模式超长报 1406，非严格模式静默截断 | 本轮临时表实测 | 字节级限长 |
| R4 | **已解除（v2.3 实测）**：声明、8 个离线 wheel、部署 venv 安装、中文 PDF 解析全链路实测均完成，详见 §0.2 | `pip list`、`_pdf_to_text` / `_fetch_file_text` 三段探针 | 传递依赖版本差异与 `/tmp` 10MB 见 §0.1 遗留 4/5 |
| R5 | 批量任务为进程内字典 + daemon 线程，多进程不一致、重启丢 | `ai_analyzer_service.py:693-705,803` | 长期改独立进程 |
| R6 | `AI_TIMEOUT=180` + 同步单条分析接口 | `.env` / `routes/ai_analysis.py:272-296` | 单条超时降级 |
| R7 | 两张皮：人工 158 条 / AI 60 条结果，互不引用 | 库统计 | G1 |
| R8 | 山东 5 个 spider 共用一个 adapter，按表而非按站点分派 | `fetch_detail_content.py:460-467` | 阶段 B 逐站核对覆盖率 |
| R9 | `config.py:80` 口令硬编码兜底 `kwd12345` | worktree `config.py` | 登记，不在本轮改 |

---

## 8. 未验成 / 待定

- 模型 `POST /v1/chat/completions` 的**成功响应未实测**（当前超时）；契约按代码反推。接口恢复后需补一次契约测试。
- 7 个站点详情页**未在本机逐站抓样**；现有 3 adapter 对山东 5 站点的覆盖率待核。
- 生产 `apache` 用户与附件目录权限**本机无法验证**；v2 设计已绕开。
- 11434 端口有监听但看不到对应进程（疑似转发 / 另一 namespace）；**v2.4 已由领导确认后端是主机关机**，不是服务崩溃，无需再排障。主机恢复后若仍超时，再查转发链路。
- 设计评审阶段所有数据库操作为**只读**，`TEXT` 探测用 `TEMPORARY TABLE` 且已 DROP，未改动任何业务数据或业务源码；v2.3 本轮动的是版本库（2 个 commit 入库 + push + worktree 快进）与部署 venv（补装 3 个 PDF 包），**未改业务逻辑代码**。
- 8 个 wheel 在**全新离线虚拟环境**中的完整安装未实测（当前只验证了部署 venv 的补装路径，传递依赖沿用旧版本）。
- 真实招标站点 PDF 附件未实测（用 soffice 生成的中文样本代替）；扫描件 / 图片型 PDF 的 OCR 路径不在现有实现内。

---

## 9. 下一步

1. **（已完成）收编 R1**：6 个 AI 文件 → commit `8a751d3`。
2. **（已完成）补齐配套改动**：2 行蓝图注册 + 4 个 PDF 依赖 → commit `26561e6`，按 hunk 精确 stage。
3. **（已完成）push + 同步分支 + 解 R4 最后一公里**：远端 `optimization` = `26561e6`；worktree 快进同步；8 个离线 wheel、venv 安装、中文 PDF 解析实测，详见 §0.2。
4. **（已完成）按 G1→G2→G3 出实现规格**：`docs/AI_IMPLEMENTATION_SPEC.md`，仍无实现代码；含 hy4 链路演练与 9 条验收判据，优先级 G2→G1→G3。
5. **（已取消）先排接口**：Ollama 是关机、不是故障，无需排障；主机恢复后补一次契约测试即可。
6. **收编规格文档**：本文档与 `.workbuddy/memory/` 仍为未跟踪，远端没有；是否单独提交待拍板。
7. **处理主工作目录剩余 32 个变更**：含 69 行安全加固、Flask/Scrapy 版本升级与 `.env.example` 口令置空，需按 hunk 分批决定范围。

---

## 10. v2.4 状态订正（2026-11-15，领导确认 Ollama 关机 + 提示可用 hy4）

**订正**：11434 后端是 **Ollama 主机关机、预期停机**，不是服务故障。此前 §2 / R2 / §8 里「接口挂了 / 根因未定位」的表述按本节覆盖。实质风险不变：停机 3 天 `failed=0`、页面无任何提示，说明缺健康检查 —— 这正是 G3 要解决的问题。

**hy4 核实**：当前会话模型 ID `hy4free`；`~/.workbuddy/models.json` 共 4 条且全部 `vendor=Ollama`
（`qwen3.8:27b` / `gemma4:26b` / `deepseek-r1:32b` / `deepseek-r1:8b`），均指向 11434，**无 hy4 条目**；
本机 8080 是要求认证的 Web 服务（401），不是模型端点。

- ⇒ 生产代码**不能**把 `AI_BASE_URL` 改成 hy4；`ai_analyzer_service.py` 需要真实 OpenAI 兼容端点。
- ⇒ 可行用法：用会话模型做**离线链路演练**（读真实库样本、按 G1 规则产出映射、验证类型与限长），不调接口、不落库。产物见 `docs/AI_IMPLEMENTATION_SPEC.md` §1.6。

**新增实测**（`bidding_info` 20 条 `ok` 结果，只读）：
`budget` / `deadline` / `purchaser` / `summary` **20/20 非空**；`risk` 17/20、`compliance` 13/20、
`scoring` 5/20、`source` 2/20。`analysis_projects.control_price` 是 `decimal(15,2)`，
而 `budget` 是自由文本（如「一标段500万元；二标段350万元；三标段350万元」）
⇒ G1 必须做金额归一化，多标段一律置 NULL，禁止猜测取第一个。

**实现规格已出**：`docs/AI_IMPLEMENTATION_SPEC.md`（G1 映射 / G2 上传 / G3 降级 + 9 条验收判据，
优先级 G2→G1→G3），不含实现代码。
