# AI 分析模块 · 生产上线清单（C75）

> 目标机：C75 `123.57.86.80`（SSH 8081）→ gunicorn 裸听 `0.0.0.0:9001`，TLS 在 frps 终结
> 代码目录：`/var/www/html/tenders`　虚拟环境：`venv312`（Web）/ `venv`（爬虫）
> 版本基线：`58ee9fd` ＋ 26 个未提交改动（**上线前必须先处理，否则会被覆盖**）

## 0. 现状与缺口（一句话版）

| 项 | 现状 | 差距 |
|---|---|---|
| 代码 | `58ee9fd`，无 AI 模块 | 缺 9 个提交（`8a751d3`…`fe6da71`） |
| 表结构 | 三张主表各 9 列 | 缺 `detail_content` / `ai_analysis` / `ai_analysis_status` / `ai_analyzed_at` |
| 依赖 | flask 3.1.3、scrapy 2.17、gunicorn 26.2 | 缺 `pdfplumber` / `pypdfium2` / `Pillow` / `pdfminer.six`（G2 上传必 500） |
| 配置 | `.env` 12 个键，无 AI 项 | 缺 `AI_BASE_URL` / `AI_MODEL` |
| 模型 | `10.140.140.170:11434`，27B，**8.2s/条** | 无缺口（生产直连，不经 C75 本机） |
| 数据量 | bidding 72375 / jiangsu 29566 / zhejiang 50837（共 15.3 万） | 全量不可行，只跑当日关键词 |
| 磁盘/内存 | 53G 可用 / 7.6G | 够 |

**口径确认**：只分析「当日发布 + 命中后台关键词」。今日 667 条 × 19% ≈ 130 条/天 ≈ 1.5 小时/天。历史 15.9 万全量 ≈ 46 天，**不做**。

## 1. 前置（5 分钟，全部只读）

```bash
# 1) 模型可达 + 出词
curl -s -m 10 http://10.140.140.170:11434/api/tags | head -c 120
# 2) 昨天的备份在
sudo ls -lht /home/mariadb_backup/files | head -4     # all_db_YYYYMMDD.sql.gz + app_var_www_html_tenders_*.tar.gz
# 3) 服务健康
systemctl is-active tenders && journalctl -u tenders -n 5 --no-pager
# 4) 生产未提交改动先存证（务必做，见步骤 2）
cd /var/www/html/tenders && git status --short > /tmp/prod-dirty-$(date +%F).txt && git diff > /tmp/prod-dirty-$(date +%F).patch
```

## 2. 代码上线

```bash
cd /var/www/html/tenders
# 2.1 26 个改动要么提交、要么打补丁留档；确认 /tmp/prod-dirty-*.patch 非空后
git stash push -u -m "prod-dirty-$(date +%F)"
# 2.2 拉取（远端已推 optimization 后执行）
git fetch origin && git checkout optimization && git merge --ff-only origin/optimization
git log --oneline -1     # 期望 fe6da71
```

## 3. 补依赖（G2 附件解析必需）

```bash
/var/www/html/tenders/venv312/bin/pip install --no-cache-dir \
  pdfplumber==0.11.9 pdfminer.six==20251230 Pillow==12.2.0 pypdfium2==5.6.0
/var/www/html/tenders/venv312/bin/python -c "import pdfplumber,PIL,pypdfium2,pdfminer;print('deps ok')"
```

## 4. 表结构补 4 列（逐表，先最小表试）

```sql
-- 先在最慢最小的表上试（zhejiang 50837 行 / 14MB）
ALTER TABLE zhejiang_bidding_info
  ADD COLUMN detail_content MEDIUMTEXT DEFAULT NULL,
  ADD COLUMN ai_analysis LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  ADD COLUMN ai_analysis_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  ADD COLUMN ai_analyzed_at DATETIME DEFAULT NULL,
  ALGORITHM=INSTANT;
```

- 成功再对 `bidding_info`（72375 行 / 25MB）、`jiangsu_bidding_info`（29566 行 / 8MB）执行。
- `ALGORITHM=INSTANT` 报错就去掉该子句重试（走 COPY，72k 行约十几秒，仍可接受）。
- **不加** `CHECK (json_valid(ai_analysis))`：开发库有，生产首版不加，避免 COPY 重建 + 历史脏值风险；应用侧本来就只写 `json.dumps`。
- 校验：`SHOW COLUMNS FROM bidding_info LIKE 'ai_%';`（期望 3 行）＋ `LIKE 'detail_content'`。

## 5. 配置与 gunicorn

```bash
# 5.1 .env 追加（值按内网实际填，勿提交仓库）
sudo -u apache tee -a /var/www/html/tenders/.env <<'EOF'
AI_BASE_URL=http://10.140.140.170:11434/v1
AI_MODEL=qwen3.8:27b
EOF

# 5.2 请求行上限：默认 4094，前端整页 project_key 能到 6~7KB → 414（7 天已 197 次）
sudo sed -i 's#--max-requests-jitter 100#--max-requests-jitter 100 --limit-request-line 8190#' \
  /etc/systemd/system/tenders.service
sudo systemctl daemon-reload && sudo systemctl restart tenders
systemctl is-active tenders && journalctl -u tenders -n 3 --no-pager
```

## 6. 验收（7 项，缺一项不带量）

| # | 检查 | 命令 / 判据 |
|---|---|---|
| 1 | 服务起 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9001/auth/login` → 200 |
| 2 | AI 页在 | 登录后打开 `/ai-analysis/` → 200，主页头部有「AI 分析」入口 |
| 3 | 模型连通 | `/ai-analysis/api/model-health?force=1` → `reachable: true`（探测超时 3s，正常毫秒级） |
| 4 | 单条出词 | 任选一条点「重新分析」→ 20~30s 出 JSON，`ai_analysis_status='ok'` |
| 5 | 批量不被回收 | 起 limit=5 → `/api/task` 连续 10 次轮询同一 `task_id`，worker 重启后仍可见 |
| 6 | 超长请求行已消失 | `journalctl -u tenders --since "-10min" \| grep -c "Request Line is too large"` → 0；列表页星标正常亮 |
| 7 | 上传解析通 | 详情弹窗上传一个 PDF → 200 且 `extracted_chars > 0`（验证第 3 步依赖） |

## 7. 首批次（当天即可跑）

```bash
# 7.1 先探 5 条，确认单条耗时与错误率
#     （页面「批量分析」按钮即同口径：today_only=1 & keywords_only=1）
# 7.2 观察：SELECT status,COUNT(*) FROM bidding_info
#     WHERE publish_date=CURDATE() GROUP BY status;
# 7.3 无 failed 再放到 limit=200 跑完当天
```

## 8. 回滚（三级，按代价排序）

| 级别 | 动作 | 影响 |
|---|---|---|
| L1 代码 | `git checkout 58ee9fd && systemctl restart tenders` | 秒级；4 列保留、旧代码不读，无副作用 |
| L2 配置 | 去掉 `--limit-request-line`、注释 AI_* 两行 → restart | 秒级；批量接口自动 503（G3 已实现） |
| L3 数据 | `zcat /home/mariadb_backup/files/all_db_YYYYMMDD.sql.gz \| mysql` | **丢当日增量**，最后手段，先停 gunicorn |

## 9. 风险表

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 生产 Flask **3.1.3** vs 本地 2.3.3 | 中 | 接口行为差异 | 上线前在生产 venv 跑 `python -m unittest discover -s tests`（97 条） |
| ALTER 期间锁表 | 低 | 写阻塞十几秒 | 02:00–05:00 窗口；先最小表 |
| gunicorn 26.2 vs 实测 27.0.1 | 低 | `--limit-request-line` 两版一致 | 已在 27 验证，26 同参数存在 |
| 模型主机单点关机 | 中 | 批量全停 | 已实现 G3：健康检查失败直接 503 不空等，页面不受影响 |
| 11434 无鉴权 | 中 | 内网裸奔 | 确认 frps 未把 11434 映射到公网；仅内网/隧道可达 |
| 15 万历史积压被误触发全量 | 低 | 跑 46 天 | 批量入口固定 `today_only`，不提供全量按钮 |

---

## 10. 上线实录（2026-11-16 22:06–22:22，已执行）

**上线版本 `23b5a38`**（不是原计划的 `fe6da71`）。执行中发现生产那 26 个未提交改动不是垃圾，
而是一条**正在线上运行的安全加固线**，直接 stash 拉代码会把它拆掉，故改为先收编再合并。

### 10.1 与原计划的 4 处偏离

| # | 原计划 | 实际做法 | 原因 |
|---|---|---|---|
| 1 | `git stash` 后 ff 拉 `fe6da71` | 先提交为 `1645db2`，再在本地合并出 `23b5a38`，生产 ff | 那 26 个改动含全局登录拦截/CSP/XSS 转义/依赖升级，stash 掉等于摘护栏 |
| 2 | 直接 `git fetch origin` | 本地打增量 bundle → scp → `fetch <bundle>` | 生产仓库属主 `apache`，无 `~/.ssh` 密钥；且工作区文件 root 所有，`git` 需以 root + `safe.directory` 跑 |
| 3 | 未涉及 | 恢复 focus/main 写接口的 CSRF 保护（仅 `api_check` 豁免） | 安全线的测试要求这些接口无 token 返回 400；已给 jiangsu/zhejiang 的 `/api/keywords` 补 `X-CSRFToken`，否则线上加关键词按钮是坏的 |
| 4 | 未涉及 | `security.py` 换成主仓较新版本（≥12 位，不强制字符类） | 生产那份是旧版（≥9 位 + 必须含字母数字），与其自带 301 行测试自相矛盾 |

### 10.2 执行结果

| 步骤 | 结果 |
|---|---|
| 代码 | `58ee9fd → 23b5a38`，工作区干净（仅 `venv312/` 未跟踪） |
| 依赖 | venv312 装 pdfplumber 0.11.9 / pdfminer.six 20251230 / Pillow 12.2.0 / pypdfium2 5.6.0 |
| 表结构 | 三表各补 4 列，`ALGORITHM=INSTANT` 全部 <0.2s；行数 74828 / 31583 / 53261 未变 |
| 配置 | `.env` 追加 `AI_BASE_URL` / `AI_MODEL`（24→26 行）；systemd 加 `--limit-request-line 8190` |
| 服务 | `active`，gunicorn 26.2.0 正常重启，监听 0.0.0.0:9001 |

### 10.3 验收（7 项）

| # | 项 | 实测 |
|---|---|---|
| 1 | 服务起 | `/auth/login` → 200 |
| 2 | AI 页在 | `/ai-analysis/` → 200（39 KB），未登录 302 → 登录页 |
| 3 | 模型连通 | `reachable=True`，`http://10.140.140.170:11434/api/tags` |
| 4 | 单条出词 | bidding_info id=80563，**20.4s** 出 JSON，`status=ok` |
| 5 | 批量独立进程 | task 1：pid 433175 **ppid=1**，`done 4/4`，ok=4，failed=0，深入分析 4，22:17:41 完成 |
| 6 | 超长请求行 | 重启后 414 计数 **0**（最后一次 22:03:50，重启前）；POST 查重 200 |
| 7 | 上传解析 | `_bytes_to_text` 解析测试 PDF → `('Acceptance PDF 12345', 'pdf')` |

**当日候选**：山东 420 + 江苏 164 + 浙江 134 = **718 条**（`today_only` + 关键词命中口径）。

### 10.4 已知遗留

- 生产单测 **113/114 通过**，`test_access_code_has_no_hardcoded_runtime_default` 失败：
  该用例只从 `os.environ` 剔除 `ANALYSIS_ACCESS_CODE`，但 `Config` 会读 `.env`，而生产 `.env` 必然设了该值。
  属**测试自身对环境敏感**，与代码无关；要修就改测试（改用临时 cwd/临时 .env）。
- `venv312/` 未纳入 `.gitignore`，`git status` 永远有 1 条未跟踪目录；建议补一行。
- 生产 `git stash@{0}`（`prod-dirty-2026-11-16-2206`）保留未删，内容已全量提交在 `1645db2`，确认无误后可 `git stash drop`。

### 10.5 回滚（更新后）

| 级别 | 动作 | 说明 |
|---|---|---|
| L1 代码 | `git -c safe.directory='*' reset --hard 58ee9fd && systemctl restart tenders` | **需 root**；4 列与 `.env` AI 键保留无副作用；会一并失去安全加固线的合并结果 |
| L2 配置 | 去掉 `--limit-request-line`、删 `AI_*` 两行 → `daemon-reload && restart` | 批量入口自动 503 |
| L3 数据 | `zcat /home/mariadb_backup/files/all_db_20261116_020001.sql.gz \| mysql` | 丢当日增量，先停 gunicorn |

**本次备份留档**：`~/prod-dirty-2026-11-16-2200.patch`（63 KB）、`~/prod-untracked-bak-2026-11-16-2206/`、
`~/env.bak-2026-11-16-2212`、`~/tenders.service.bak-2026-11-16-2213`。
## 11. 批量改成「跑完为止」（2026-11-16 23:20 上线）

原实现一次只取 limit 条就结束，用户得反复点按钮；且 `ai_analysis_status='failed'` 不会被排除，
一批稳定失败的记录每次都被重新选中，正常记录永远排不进来（表现成「反复跑、成功 0」）。

| 项 | 改法 | 上线动作 |
|---|---|---|
| 单轮 → 多轮 | `run_batch` 内 `while` 重取，直到 `pick_rows` 返回空；`MAX_ROUNDS=30` 硬顶 | 只换代码 |
| 总闸 | 页面按「每批条数 × 10」传 `max_total`（后端 clamp 1..2000），runner 收 `--max-total` | 只换代码 |
| 失败不重挑 | 失败 id **按表**记进 `excluded`（id 跨表会重复），后续轮次 `id NOT IN (...)` | 只换代码 |
| 空正文不算候选 | `has_content` 由 `detail_content IS NOT NULL` 收紧为 `... AND <> ''`；抓取侧空串也重抓 | 只换代码（无 DDL） |
| 软停止 | `POST /ai-analysis/api/stop` → 任务 `status='stopping'`；任务进程每条前查一次后收尾；`get_latest` 仍返回 `running=True`，进度条不会假完成 | 只换代码（无 DDL） |

**开发机验证**：`python -m unittest discover -s tests` → 114 OK（新增 `tests/test_ai_batch_loop.py` 8 条）；
真库跑过一次停止状态机（`try_start → request_stop → stopping → finish`）。

**上线注意**：`tools/ai_coverage.py backfill` 的外层轮次已冗余（内层自己会跑完），行为正确、输出「第 2 轮」起显示 0 条属正常。

