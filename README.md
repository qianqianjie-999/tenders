# Tenders 招标信息管理系统 V1

自动采集各地市招标公告的爬虫平台，提供 Web 界面进行数据查看、筛选、关注和分析。

---

## 功能特性

- 多地区招标信息自动采集（山东省各地市、江苏省）
- 数据可视化仪表盘
- 重点关注项目管理
- 标书分析（开标日期、控制价等）
- 爬虫运行监控与日志记录
- 数据导出（CSV）
- 关键词高亮与搜索

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端框架 | Flask 2.3.3 |
| 爬虫框架 | Scrapy 2.11.0 |
| 数据库 | MySQL 5.7+ |
| 数据处理 | Pandas, NumPy |
| Web 服务器 | WSGI |

---

## 项目结构

```
tenders/
├── flask_web/              # Flask Web 应用
│   ├── app/
│   │   ├── routes/         # 路由
│   │   ├── services/       # 业务逻辑
│   │   └── utils/          # 工具函数
│   ├── static/             # 静态资源
│   ├── templates/          # HTML 模板
│   ├── .env                # 环境变量配置
│   └── run.py             # 启动脚本
│
├── scrapy_spider/          # Scrapy 爬虫
│   └── bidding_spider/
│       ├── spiders/        # 爬虫实现
│       ├── items.py        # 数据项定义
│       └── pipelines.py    # 数据处理管道
│
├── logs/                   # 日志目录
├── venv/                   # Python 虚拟环境
├── creat_database.sql      # 数据库建表脚本
├── requirements.txt       # Python 依赖
└── tenders.wsgi          # WSGI 配置
```

---

## 快速开始

### 1. 环境要求

- Python 3.8/3.9（推荐与生产环境保持一致）
- MySQL 5.7+
- Linux/macOS/Windows

> **注意**：依赖版本已兼容 Python 3.8 和 3.9：
> - pandas 1.5.3 + numpy 1.24.3 支持 Python 3.8/3.9
> - 如服务器使用 Python 3.9，本地开发可使用相同版本

### 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 数据库配置

```bash
# 创建数据库并导入表结构
mysql -u root -p < creat_database.sql
```

### 4. 环境变量配置

```bash
# 复制环境变量模板
cp flask_web/.env.example flask_web/.env

# 编辑配置文件
vim flask_web/.env
```

`.env` 配置项：

```env
SECRET_KEY=change_me_secret
DB_HOST=localhost
DB_USER=bidding_user
DB_PASSWORD=your_db_password
DB_NAME=bidding_db
DB_PORT=3306
ANALYSIS_ACCESS_CODE=kwd12345
```

### 5. 启动 Web 服务

```bash
cd flask_web
python run.py
```

访问地址：http://localhost:5000

---

## 爬虫使用

### 可用爬虫列表

| 爬虫名称 | 数据源 | 日期范围 | 请求方式 |
|---------|--------|----------|----------|
| `sd_post` | 山东省政府采购网 | 当天（可指定） | POST |
| `jining_get` | 济宁市公共资源交易中心 | 最近3天 | GET |
| `jinan_post` | 济南市公共资源交易中心 | 当天 | POST |
| `taian_post` | 泰安市公共资源交易中心 | 当天 | POST |
| `zibo_post` | 淄博市公共资源交易中心 | 当天 | POST |
| `jiangsu_post` | 江苏省公共资源交易中心 | 当天 | POST |

### 运行爬虫

```bash
cd scrapy_spider/bidding_spider

# 运行山东全省爬虫（默认当天）
scrapy crawl sd_post

# 指定日期运行
scrapy crawl sd_post -a target_date=2026-03-01

# 运行济宁爬虫（最近3天）
scrapy crawl jining_get
```

### 定时任务配置

```bash
# 编辑 crontab
crontab -e

# 每天凌晨 2 点运行所有爬虫
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl sd_post
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl jinan_post
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl taian_post
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl zibo_post
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl jining_get
0 2 * * * cd /path/to/tenders/scrapy_spider/bidding_spider && /path/to/venv/bin/python -m scrapy crawl jiangsu_post
```

---

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/data` | GET | 获取山东招标数据（支持分页、筛选） |
| `/jiangsu/api/data` | GET | 获取江苏招标数据（支持分页、筛选） |
| `/api/categories` | GET | 获取山东项目分类列表 |
| `/jiangsu/api/categories` | GET | 获取江苏项目分类列表 |
| `/api/sources` | GET | 获取山东数据源列表 |
| `/jiangsu/api/sources` | GET | 获取江苏数据源列表 |
| `/api/keywords` | GET/POST/DELETE | 关键词管理 |
| `/api/export` | GET | 山东 CSV 数据导出 |
| `/jiangsu/api/export` | GET | 江苏 CSV 数据导出 |
| `/focus/api/list` | GET | 获取关注项目列表 |
| `/analysis/api/list` | GET | 获取分析项目列表 |
| `/bidding/api/list` | GET | 获取投标项目列表 |
| `/monitor/api/stats` | GET | 获取爬虫统计数据 |

### 数据查询示例

```bash
# 查询指定日期数据
curl "http://localhost:5000/api/data?date=2026-03-01&page=1&page_size=10"

# 按分类筛选
curl "http://localhost:5000/api/data?category=建设工程招标公告&page=1&page_size=10"

# 按来源筛选
curl "http://localhost:5000/api/data?source=济南市&page=1&page_size=10"

# 搜索关键词
curl "http://localhost:5000/api/data?keyword=学校&page=1&page_size=10"
```

---

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `bidding_info` | 主招标信息表（山东省） |
| `jiangsu_bidding_info` | 江苏省招标信息表 |
| `focus_projects` | 重点关注项目表 |
| `tracking_records` | 项目跟踪记录 |
| `analysis_projects` | 标书分析表 |
| `bidding_projects` | 投标项目表 |
| `spider_run_logs` | 爬虫运行记录 |
| `spider_timeout_logs` | 爬虫超时错误记录 |
| `spider_daily_stats` | 爬虫每日统计汇总 |

---

## 页面功能

| 页面 | 路由 | 功能 |
|------|------|------|
| 主页（山东） | `/` | 山东省招标信息浏览，支持筛选 |
| 江苏数据 | `/jiangsu/` | 江苏省招标信息浏览，支持筛选、统计、导出 |
| 仪表盘 | `/dashboard` | 数据统计概览 |
| 关注管理 | `/focus/` | 重点关注项目管理 |
| 标书分析 | `/analysis/` | 标书分析功能（需访问码） |
| 投标管理 | `/bidding/` | 投标项目管理 |
| 监控面板 | `/monitor/` | 爬虫运行监控 |

---

## 测试

```bash
# 运行自动化测试
python test_all.py
```

---

## 日志管理

### 日志文件

日志文件位于 `logs/` 目录：

- `bidding_spider_YYYYMMDD.log` - 主爬虫日志（按日期轮转）
- `timeout_errors.log` - 超时错误记录
- `spider_stats.log` - 统计日志
- `scrapy_slow.log` - 慢请求记录
- `cron_*.log` - 定时任务日志

### 日志清理

#### 方式一：使用交互式脚本

```bash
# 运行交互式清理脚本
./cleanup.sh
```

选项：
1. 清理 7 天前的日志文件
2. 清理 30 天前的日志文件
3. 清理超过 100MB 的日志文件
4. 预览清理（不实际删除）
5. 日志轮转（备份大文件）

#### 方式二：直接使用清理脚本

```bash
# 清理 7 天前的日志
python3 clean_logs.py --dir logs --days 7

# 清理超过 100MB 的日志
python3 clean_logs.py --dir logs --size 100M

# 预览清理效果（不实际删除）
python3 clean_logs.py --dir logs --days 7 --dry-run

# 日志轮转（备份超过 10MB 的日志）
python3 clean_logs.py --dir logs --rotate --size 10M
```

### 定时清理配置

参考 `crontab_cleanup.txt` 配置自动清理任务：

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 3 点清理 7 天前的日志
0 3 * * * cd /path/to/tenders && python3 clean_logs.py --dir logs --days 7 >> logs/cleanup.log 2>&1
```

---

## 内网环境部署

### 方案一：离线包部署（推荐）

#### 1. 在外网机器准备依赖包

```bash
# 1. 下载所有依赖包（含子依赖）
mkdir packages
pip download -r requirements.txt -d ./packages --python-version 3.8 --platform manylinux1_x86_64

# 2. 打包项目代码
tar -czf tenders-v1.tar.gz --exclude='venv' --exclude='packages' --exclude='.git' .
```

#### 2. 拷贝到内网服务器

将以下文件拷贝到内网服务器：
- `tenders-v1.tar.gz`
- `packages/` 目录

#### 3. 内网服务器安装

```bash
# 1. 解压代码
tar -xzf tenders-v1.tar.gz -C /opt/tenders
cd /opt/tenders

# 2. 创建虚拟环境
python3.8 -m venv venv
source venv/bin/activate

# 3. 离线安装依赖
pip install --no-index --find-links=./packages -r requirements.txt
```

### 方案二：搭建内网 PyPI 镜像

```bash
# 1. 安装 pypiserver
pip install pypiserver

# 2. 启动服务
pypi-server -p 8080 ./packages

# 3. 配置 pip 使用内网源
pip install -i http://内网 IP:8080/simple -r requirements.txt
```

### 方案三：从内网 Git 拉取

在内网搭建 GitLab/Gitea，将代码推送到内网仓库：

```bash
# 外网机器
git remote add intranet http://内网 IP/username/tenders.git
git push intranet main

# 内网机器
git clone http://内网 IP/username/tenders.git
```

---

## 生产部署

### 使用 Gunicorn + Nginx

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务
gunicorn -w 4 -b 127.0.0.1:5000 tenders.wsgi:app
```

### Systemd 服务配置

```ini
[Unit]
Description=Tenders Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/tenders/flask_web
Environment="PATH=/path/to/tenders/venv/bin"
ExecStart=/path/to/tenders/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 常见问题

### 1. 数据库连接失败

检查 `.env` 文件中的数据库配置是否正确。

### 2. 爬虫超时过多

- 检查网络连接
- 调整爬虫的超时设置
- 检查目标网站是否可访问

### 3. 跨域问题

在 Nginx 配置中添加 CORS 头。

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 Pull Request。

---

## 联系方式

如有问题，请提交 Issue。
