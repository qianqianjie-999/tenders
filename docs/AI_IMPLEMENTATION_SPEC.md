# G1 / G2 / G3 实现规格（实现前评审稿）

- 日期：2026-11-15
- 状态：**实现规格，待评审；本文不含任何可执行的 Python / JS / SQL 实现代码**
- 上位文档：`docs/AI_ANALYSIS_DESIGN_SPEC.md` v2.3（设计规格，含实测基线与风险表）
- 前提：领导四项决策不变（① 正文+附件+人工上传 ② 内网本地、接口暂不通 ③ 复用 `analysis_content` ④ 转入分析时触发）
- 本轮新增事实：Ollama **是主机关机、属预期停机**（非服务故障）；当前会话模型 `hy4free` 无本地 OpenAI 兼容端点

---

## 0. 本轮实测事实（写规格前先核过的）

| 项 | 结论 | 证据 |
|---|---|---|
| hy4 接口形态 | 会话模型 ID 为 `hy4free`；`~/.workbuddy/models.json` 共 4 条，**全部 vendor=Ollama**，均指向 `http://127.0.0.1:11434/v1/chat/completions`，**无 hy4 条目**；8080 是另一个要求认证的 Web 服务（401），不是模型端点 | 环境变量 + 配置结构只读解析 + HTTP GET 探测 |
| 生产代码不能直接接 hy4 | `ai_analyzer_service.py` 走 OpenAI 兼容 `POST /v1/chat/completions`；hy4 没有可直连端点，硬改 `AI_BASE_URL` 只会制造新的失败源 | 接口契约 + 端点探测 |
| **hy4 的正确用法** | 用会话模型做**离线链路演练**：读真实库样本 → 按 G1 规则产出结构化映射结果 → 验证字段类型与限长。**不调接口、不落库** | 本文 §1.6 即演练产物 |
| AI 结果字段覆盖率 | `bidding_info` 中 20 条 `ok` 结果：`budget` / `deadline` / `purchaser` / `summary` **20/20 非空**；`risk` 17/20、`compliance` 13/20、`scoring` 5/20、`source` 2/20 | 只读库统计（另两张地区表各 20 条，合计 60 条） |
| 目标表字段类型 | `control_price decimal(15,2)`、`bid_open_date date`、`tenderer varchar(200)`、`analysis_content text`、`decision varchar(20)` | `information_schema.columns` |
| 人工侧现状 | `analysis_content` 多为极短备注（如「资质不符」「商务失8分」）；`control_price` / `bid_open_date` / `tenderer` 全 NULL；`decision=pending` | 只读样本 |
| 接口当前状态 | 11434 TCP 仍监听，但 `/api/tags`、`/v1/models` HTTP 超时 —— 与「Ollama 主机关机」一致 | 端口 + HTTP 探测 |

**由此产生的规格修正**：G1 的输入不是「调模型」，而是**反查已落库的 `ai_analysis` JSON**；因此接口关机期间 G1 仍可完整工作。G3 的降级目标从「修故障」改为「让停机可见」。

---

## 1. G1 · 转单打通两条链（决策 ③④）

### 1.1 触发点与执行边界

- 触发点不变：`focus.py:177` 的转入分析接口，仍同步秒回 `analysis_id`。
- 同一事务内：创建 `analysis_projects` 行 → 按 `detail_url` 反查主表 AI 结果 → 回填 → 提交。
- **禁止**在请求内做详情页抓取、附件下载或模型调用；接口关机、超时都不影响转单成功。
- AI 回填逻辑整体包在独立异常边界内：任何解析失败只记日志、字段留空，不得让转单失败。

### 1.2 反查规则

按 `project_source` / 表前缀分派到三张地区主表，取 `ai_analysis_status='ok'` 且 `ai_analysis` 非空的最新一条。
查不到 → 转单照常成功，AI 字段留空，页面显示「暂无 AI 结果」（不写 `failed`、不触发分析）。

### 1.3 字段映射表（hy4 演练后定稿）

| 目标列 | 类型 | 源字段 | 规则 | 失败 / 歧义处理 |
|---|---|---|---|---|
| `control_price` | `decimal(15,2)` | `budget` | 见 §1.4 金额归一化 | **置 NULL**，预算原文写入结论，禁止猜测 |
| `bid_open_date` | `date` | `deadline` | 取前 10 位 `YYYY-MM-DD` | 置 NULL；并在结论标注「源为投标截止时间，非开标日」 |
| `tenderer` | `varchar(200)` | `purchaser` | 直接取；超 200 字符截断 | 置 NULL |
| `analysis_content` | `text` | `summary` + `risk` / `compliance` / `scoring` | 见 §1.5 | 只写摘要段 |
| `decision` / `decision_reason` | — | — | **不自动写**，保留 `pending` | — |
| `agency` | — | `agency` | **不映射到 tenderer**（代理机构≠招标人） | — |

> `agency` 的坑有代码佐证：`fetch_detail_content.py:339` 明确注释「userName 是代理机构（不是招标人）」。

### 1.4 金额归一化（实测最大难点）

`budget` 是**自由文本，不是数字**，直接塞进 `decimal` 会报错：

| 真实样本 | 处理 |
|---|---|
| `20万元` | 解析为 `200000.00`，写入 `control_price` |
| `一标段500万元；二标段350万元；三标段350万元` | **多标段 → 单一 decimal 无法表达 → 置 NULL**；把「总预算 1200 万元 / 三个标段」写进结论 |

统一规则：仅当文本能解析出**唯一金额**（支持 `元` / `万元` / 千分位 / 小数点）才写 `control_price`；多标段、区间、上限+下限、含「详见招标文件」、单位不明一律 NULL。宁可空着，不可猜。

### 1.5 结论拼接、限长与安全

拼接为**纯文本**，固定段序：AI 摘要 → 风险（逐条）→ 合规（逐条）→ 评分（逐条，空则整段省略）→ 溯源（模型名、分析时间、预算原文、截止时间语义标注）。

| 约束 | 值 / 做法 | 依据 |
|---|---|---|
| 字节上限 | UTF-8 **< 60,000 B** | 生产 MariaDB 10.11.14 + `STRICT_TRANS_TABLES` 实测：65,535 B 通过、65,536 B 报 **1406**；中文 22,000 字同样报错 |
| 非空不覆盖 | 人工 `analysis_content` 非空时**不写入**，AI 结果仅作「待采纳」提示 | `analysis.py:187-191` 是覆盖式 UPDATE，无版本表；人工结论冲掉不可回滚 |
| 渲染转义 | AI 文本中的 `<` `>` `&` 必须转义，或改用 `textContent` 渲染 | `analysis.html` 用模板字符串直出（`${item.analysis_content}`），AI 文本带标签即 XSS |
| 不生成 HTML | 拼接结果只允许换行与纯文本，禁止富文本标签 | 同上 |

### 1.6 hy4 链路演练结果（会话模型 `hy4free` 产出，**未落库**）

| 公告 ID | 项目 | `budget` → `control_price` | `deadline` → `bid_open_date` | `purchaser` → `tenderer` |
|---|---|---|---|---|
| 403 | 《沂蒙革命根据地简史》出版服务采购 | `20万元` → `200000.00` | `2026-11-26 09:30` → `2026-11-26`（标注：截止时间） | 华东革命烈士陵园管理服务中心（沂蒙革命纪念馆） |
| 404 | 河东区城区市政道路日常维修维护 | 三标段 → **NULL**（结论保留「总预算 1200 万元 / 一标段 500 万、二/三标段各 350 万」） | `2026-12-03 09:00` → `2026-12-03`（标注：截止时间） | 临沂市河东区综合行政执法局 |

演练结论：**20/20 的 `budget` / `deadline` / `purchaser` 都可用，但只有「唯一金额」才能进 `decimal`**；`risk` / `compliance` / `scoring` 缺失率分别为 15% / 35% / 75%，拼接时必须容忍空数组。

### 1.7 鉴权（实现前必核）

- `focus.py:177` 补 `require_auth_write`（登录 + 访问口令双门槛）。
- **不能照抄 worktree 版装饰器链**：主工作目录版 `__init__.py` 已删除 focus/main 的 CSRF 豁免（含 `csrf.exempt(api_move_to_analysis)`），限流豁免重构为 `_rate_limit_exempt()`。实现前按主工作目录版本复核实际装饰器与豁免关系。

### 1.8 事务与失败边界

单事务内完成「建行 + 回填」；AI 部分单独异常边界，失败降级为空值并记日志（含公告 ID、源字段、失败原因）。
不新增任务表、不引入队列 —— v1 的 3 张旁路表已作废，现有 `pending/ok/failed` 三态足够。

---

## 2. G2 · 人工上传（决策 ① 第三路）

| 项 | 规格 |
|---|---|
| 入口 | 分析页新增「上传附件」，沿用登录 + 访问口令双门槛 |
| 接受类型 | PDF / doc / docx / xls / xlsx，**按文件头判定**（PDF `%PDF`、docx `PK`、老 doc OLE2），不信任扩展名 |
| 复用 | `fetch_detail_content.py:354-364` 的 `_pdf_to_text`、`:370-389` 的 `_doc_to_text`、`:392-404` 的判头分支 |
| 存储 | **只存解析文本，不落盘原件**（绕开生产 `apache` 权限与 `/static` 被 Apache Alias 直出绕过鉴权两个坑） |
| 写入 | 与 §1.5 同一套限长 + 转义 + 非空不覆盖规则 |
| 依赖 | 4 个 PDF 包已在部署 venv 离线安装并实测通过（设计规格 §0.2：中文 PDF 154 字提取、`%PDF` 判头分支、非 PDF 返回空，三段全 PASS） |
| 定位 | **接口关机期唯一可用输入**，必须先于 G1 的正文抓取补完即可独立工作 |

**实现时必须同时处理的长稳项**：`_doc_to_text` 用 `tempfile.TemporaryDirectory()` 且 LibreOffice profile 写死 `/tmp/lo_prof_*`（`fetch_detail_content.py:375-379`）；本机 `/tmp` 是 **10 MB tmpfs**，大附件转换会失败。需把临时目录指向大分区、profile 放独立可写目录。

---

## 3. G3 · 接口降级与可观测（决策 ②）

**状态订正**：Ollama 是**主机关机、预期停机**，不是服务故障。但「`failed=0`、停机 3 天无人发现」这一**健康检查缺失**的实质风险不变。

| 能力 | 规格 |
|---|---|
| 状态机 | 复用现有 `pending` / `ok` / `failed`；新增 `unavailable`（服务不可达）展示态，不新增列时用日志/页面标记区分 |
| 健康检查 | 启动与定时探测 `/api/tags` 或 `/v1/models`，短超时；不可达即置 `unavailable`，页面显式提示「模型主机关机」 |
| 错误分类 | 连接拒绝 / 超时 → `unavailable`（可重试）；4xx → 参数或模型名错误（不重试）；5xx / 空响应 / JSON 解析失败 → `failed` |
| 批量行为 | 遇 `unavailable` **跳过并保留 pending**，不得批量写 `failed`（否则一次关机会污染全部待分析数据） |
| 单条超时 | `AI_TIMEOUT=180` 对同步单条接口过长，改为可配置短超时；批量任务仍可保留长超时 |
| 配置 | 复用现有 4 键 `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY` / `AI_TIMEOUT`，**不新增配置项** |
| hy4 接入 | **非本轮范围**。要接需先有 OpenAI 兼容端点；当前 `models.json` 无 hy4 条目，只能做离线注入（§1.6 演练方式），不可把 `AI_BASE_URL` 硬指向会话模型 |

---

## 4. 不在本轮范围 / 遗留

- 不新增旁路表、不改主表 DDL、不动 `items.py` / `pipelines.py`。
- 不做模型版本 / 置信度 / 历史版本表；若要「AI 结果可回滚、可采纳」，需另开一轮设计。
- 不做 OCR：扫描件 / 图片型 PDF 不在现有能力内。
- 不实现详情页逐站抓取改造（现有 3 adapter 覆盖率待核，属设计规格 R8）。
- **不写任何实现代码**。

---

## 5. 验收判据（可测，全部不依赖模型开机）

| 编号 | 判据 | 验证方法 |
|---|---|---|
| A1 | 有 / 无 AI 结果时转单均秒回，且请求内不发起任何模型或外网抓取 | 关机状态转单 2 条，计时 + 查日志 |
| A2 | 唯一金额写 `control_price`，多标段置 NULL | 用 §1.6 的 403 / 404 两条样本 |
| A3 | 已有人工结论不被覆盖 | 预置非空 `analysis_content` 再转单 |
| A4 | AI 文本含 `<script>` 时页面不执行 | 转义渲染检查 |
| A5 | 单次写入 `LENGTH()` < 60,000 B | 只读库校验 |
| A6 | 未登录 / 无访问口令均被 `require_auth_write` 拦截 | 各请求一次 |
| A7 | 上传中文 PDF 能提取文本 | 复用设计规格 §0.2 探针 |
| A8 | 接口不可用时批量任务保持 `pending`、不写 `failed` | 关机状态跑一次批量 |
| A9 | `agency` 不被误写进 `tenderer` | 检查 403 样本（代理机构与招标人不同） |

---

## 6. 改动面清单（预估，供排期）

| 文件 | 动作 | 依赖 |
|---|---|---|
| `flask_web/app/routes/focus.py` | 补鉴权 + 反查回填 + 异常降级 | 无 |
| `flask_web/templates/analysis.html` | 上传入口、状态展示、结论转义渲染 | G2 |
| `flask_web/app/routes/ai_analysis.py` | 上传接口、健康检查、错误分类、超时收敛 | G2/G3 |
| `tools/fetch_detail_content.py` | 仅改 `_doc_to_text` 临时目录指向（长稳项） | 需单独评审 |
| `__init__.py` / `config.py` | **尽量不动**；超时优先复用 `.env` | — |
| 明确不改 | 主表 DDL、`items.py`、`pipelines.py`、模型服务本身 | — |

优先级：**G2 → G1 → G3**。G2 不依赖模型开机，先做完就能在关机期独立跑通输入；G1 是四项决策里唯一还没落地的部分；G3 收尾解决「停机不可见」。

---

## 7. 没验成的

- hy4 的 OpenAI 兼容端点（本机未找到；若后续由 WorkBuddy 暴露，需补一次契约测试再谈接入）。
- 模型 `POST /v1/chat/completions` 的成功响应（主机关机，契约按代码反推）。
- 另两张地区表各 20 条 AI 结果的字段覆盖率（本轮只统计了 `bidding_info` 的 20 条）。
- 真实招标站点 PDF 附件（设计规格 §0.2 用的是 soffice 生成的中文样本）。
- 主工作目录剩余 32 个变更的实现完成度与测试状态（本轮只做分类与脱敏扫描，未提交代码类改动）。
