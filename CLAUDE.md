# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

招标信息爬虫平台，采集山东省各地市和江苏省的招标公告数据，提供 Web 界面进行查看、筛选和分析。

**技术栈**: Flask 2.3.3, Scrapy 2.11.0, MySQL 5.7+, Pandas 1.5.3, NumPy 1.24.3

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
mysql -u root -p < creat_database.sql

# 启动 Web 服务
cd flask_web && python run.py

# 运行爬虫
cd scrapy_spider/bidding_spider
scrapy crawl sd_post           # 山东省政府采购网
scrapy crawl jining_get        # 济宁市公共资源交易中心
scrapy crawl jinan_post        # 济南市公共资源交易中心
scrapy crawl taian_post        # 泰安市公共资源交易中心
scrapy crawl zibo_post         # 淄博市公共资源交易中心
scrapy crawl jiangsu_post      # 江苏省公共资源交易中心

# 指定日期运行爬虫
scrapy crawl sd_post -a target_date=2026-03-01

# 运行测试
python test_all.py

# 清理日志
python3 clean_logs.py --dir logs --days 7
```

## 项目结构

```
tenders/
├── flask_web/              # Flask Web 应用
│   ├── app/
│   │   ├── routes/         # 路由蓝图 (main, jiangsu, focus, analysis, bidding, dashboard, monitor)
│   │   ├── services/       # 业务逻辑 (bidding_service, jiangsu_service, focus_service, keyword_service)
│   │   ├── models/         # 数据库模型
│   │   └── utils/          # 工具函数
│   ├── templates/          # HTML 模板
│   ├── static/             # 静态资源
│   └── run.py              # 启动脚本
├── scrapy_spider/bidding_spider/
│   ├── bidding_spider/
│   │   ├── spiders/        # 爬虫实现 (*_post.py, *_get.py)
│   │   ├── pipelines.py    # 数据入库 (支持多表映射)
│   │   ├── middlewares.py  # 请求中间件 (超时重试、用户代理)
│   │   └── settings.py     # Scrapy 配置
│   └── logs/               # 爬虫日志
├── logs/                   # 应用日志
└── creat_database.sql      # 数据库表结构
```

## 数据架构

**核心表**:
- `bidding_info` - 山东省招标数据
- `jiangsu_bidding_info` - 江苏省招标数据 (独立表)
- `focus_projects` - 重点关注项目
- `analysis_projects` - 标书分析
- `bidding_projects` - 投标项目
- `spider_run_logs` - 爬虫运行记录
- `spider_timeout_logs` - 超时错误记录
- `spider_daily_stats` - 每日统计

**Pipeline 表映射** (`pipelines.py`):
```python
spider_table_mapping = {
    'jiangsu_post': 'jiangsu_bidding_info',
    'sd_post': 'bidding_info',
    'jining_get': 'bidding_info',
    'taian_post': 'bidding_info',
    'jinan_post': 'bidding_info',
    'zibo_post': 'bidding_info'
}
```

## 配置说明

**环境变量** (`.env`):
```env
SECRET_KEY=your-secret-key
ANALYSIS_ACCESS_CODE=access-code
FLASK_DEBUG=false
DB_HOST=localhost
DB_USER=bidding_user
DB_PASSWORD=xxx
DB_NAME=bidding_db
DB_PORT=3306
LOG_JSON=false
LOG_BACKUP_DAYS=7
```

**Scrapy 配置要点** (`settings.py`):
- `CONCURRENT_REQUESTS = 4` - 并发限制
- `DOWNLOAD_DELAY = 1` - 下载延迟
- `DOWNLOAD_TIMEOUT = 30` - 超时设置
- `AUTOTHROTTLE_ENABLED = True` - 自动限速

## 新增爬虫步骤

参考 `SPIDER_MONITOR_GUIDE.md`，核心步骤:
1. 在 `spiders/` 目录创建爬虫文件
2. 导入 `monitor_db` 模块实现监控埋点
3. 在 `pipelines.py` 添加表映射
4. 在 `settings.py` 或爬虫中配置目标网站规则
5. 添加 crontab 定时任务

## 定时任务

参考 `crontab_server.txt` 和 `crontab_local.txt`，爬虫按小时交错运行避免并发过高。

## 用户认证

系统采用全局登录保护，所有页面访问前都需要先登录。

**登录流程**:
1. 访问任意页面（如 `/`, `/analysis/`, `/bidding/`）自动重定向到 `/auth/login`
2. 使用用户名和密码登录
3. 登录成功后重定向回原页面或主页

**配置用户**:
```bash
# 生成密码哈希
python tools/generate_password.py 用户名 密码

# 编辑 .env 添加 USERS_CONFIG
USERS_CONFIG=admin:密码哈希
```

**默认账号**: `admin` / `admin123`（首次登录后建议修改）

**受保护页面**: 所有页面（主页 `/`、分析标书 `/analysis/`、投标项目 `/bidding/` 等）

**自动记录操作人**: 登录后，所有更新操作自动记录当前用户名为操作人
