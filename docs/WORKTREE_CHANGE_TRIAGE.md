# 主工作目录剩余变更 · 分批收编清单

- 日期：2026-11-15
- 范围：`/home/qianqianjie/tenders`（`optimization` 分支）`git status --short` 的 **32 个条目**
  = 25 个已修改文件 + 14 个未跟踪文件（按目录合并显示为 7 个条目）
- 状态：**本轮只分类 + 脱敏，未提交任何代码类改动**；3 份规格文档已单独收编
- 依据：`git status --short`、`git diff --numstat`、逐行脱敏扫描（只报类别与行号，不输出值）

---

## 1. 分组结论（建议按此顺序拍板）

| 组 | 内容 | 文件数 | 行数规模 | 风险 | 建议 |
|---|---|---|---|---|---|
| **C · 爬虫修复** | `items.py`(0/1)、`pipelines.py`(3/3)、`spiders/jiangsu_post.py`(6/6)、`spiders/zibo_post.py`(13/8)、`tests/test_spider_regressions.py`(新) | 5 | 约 30 行 | **低**，有配套回归测试 | **优先收编**，先跑 `unittest discover` 再提交 |
| **A · 安全加固 / 用户管理** | `__init__.py`(69/15，其中 2 行蓝图注册已入库)、`config.py`(3/3)、`decorators.py`(4/3)、`admin.py`(19/6)、`auth.py`(15/6)、`main.py`(3/2)、`helpers.py`(11/3)、`utils/security.py`(新)、6 个模板(index/jiangsu/zhejiang/dashboard/analysis/monitor 共 219/67)、`tests/test_security_hardening.py`(新)、`.trae/documents/user-management-overhaul.md`(新) | 约 18 | 约 350 行 | **高**：改鉴权与装饰器链，且主工作目录版已删 focus/main 的 CSRF 豁免、重构 `_rate_limit_exempt()` | 需先跑安全测试；**逐文件核 diff 后再按 hunk 提交** |
| **B · 部署 / 运维 / 版本升级** | `requirements.txt`(24/9，Flask 2.3.3→3.1.3、Scrapy 2.11→2.17、加 gunicorn)、`README.md`(20/2)、`docs/TESTING_AND_MONITORING.md`(38/1)、`docs/DEPLOYMENT.md`(新)、`docs/FRP_C75_INCIDENT_2026-10-27.md`(新)、`deploy/*.sh` 4 个 + `deploy/systemd/*` 4 个、`monitor.py`(36/5)、`monitor_service.py`(23/3)、`monitor_db.py`(24/0) | 约 17 | 约 250 行 + 8 个脚本 | **高**：大版本升级改变运行行为；部署脚本涉及 systemd / gunicorn 切换 | 单独评审 + 回归；**文档与代码不要拆开提交**（会不一致） |
| **D · 工具产物** | `.trae-html-share-packages/flask_web/templates/ai_analysis.html.zip`、`.trae/` | 2 组 | 二进制 + 笔记 | 无代码风险，但**不该入库** | 加 `.gitignore` 规则，或明确保留为本地文件 |

**为什么没有一次性全提交**：32 个变更是三批独立工作混在一起；B 组含框架大版本升级、A 组改鉴权，两者都需要测试或回归。一次性 `git add -A` 会把它们和工具产物捆成一个无法回滚的提交，也不符合之前按 hunk 精确收编的约定。

---

## 2. 脱敏扫描结果（逐文件，只报类别与行号）

| 位置 | 命中 | 判定 |
|---|---|---|
| `.env.example:19` | `DB_PASSWORD=<占位符>` | **占位符**，与生产 `.env` 真口令不同（`SAME_AS_REAL_ENV=False`） |
| `README.md:107` | `DB_PASSWORD=<示例串>` | 非占位符，但**不等于生产真口令**；建议改成占位符后再提交 |
| `docs/TESTING_AND_MONITORING.md:213` | `"ip": "<内网地址>"` | **私有地址**，非公网 IP；可接受 |
| 其余 `deploy/*`、`docs/*`、测试、`security.py` | 0 命中 | 无硬编码口令 / 私钥 / `sk-` 令牌 |

扫描覆盖：口令赋值、私钥头、`sk-` 令牌、私网 IP、SSH user@IP、公网 IP；**只输出类别与行号，未输出任何值**。

---

## 3. 本轮实际收编了什么

| 文件 | 位置 | 动作 |
|---|---|---|
| `docs/AI_ANALYSIS_DESIGN_SPEC.md` | worktree | 提交（v2.4，含 §10 状态订正） |
| `docs/AI_IMPLEMENTATION_SPEC.md` | worktree | 提交（G1/G2/G3 实现规格） |
| `docs/WORKTREE_CHANGE_TRIAGE.md` | worktree | 提交（本清单） |

**主工作目录 32 个变更一个都没提交**；`.workbuddy/memory/` 为会话记忆目录，不入库。

---

## 4. 下一批请拍一个编号

1. **C 组**：先跑爬虫回归测试，通过后按 hunk 提交 5 个文件。
2. **A 组**：先跑 `tests/test_security_hardening.py`，逐文件核 diff 后再提交（工作量最大）。
3. **B 组**：单独评审 Flask/Scrapy 版本升级与部署脚本，需回归环境。
4. **D 组**：只加 `.gitignore` 规则，消除工具产物噪音。
5. **全部由我按组顺序依次提交**：每组提交前给清单，您逐组确认。

> 任何一组提交都只做本地 commit、**不 push**；push 前会另列清单。
