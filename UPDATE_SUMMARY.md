# 江苏省爬虫功能更新文档

## 更新时间
2026-03-19

## 新增功能

### 1. 数据库表
- **表名**: `jiangsu_bidding_info`
- **说明**: 江苏省招标信息独立表，与山东省数据隔离
- **位置**: `creat_database.sql` 末尾

### 2. 爬虫
- **爬虫名称**: `jiangsu_post`
- **数据源**: 江苏省公共资源交易中心 (http://jsggzy.jszwfw.gov.cn)
- **位置**: `scrapy_spider/bidding_spider/bidding_spider/spiders/jiangsu_post.py`
- **运行命令**: 
  ```bash
  cd scrapy_spider/bidding_spider
  scrapy crawl jiangsu_post
  ```

### 3. Pipeline 改造
- **文件**: `scrapy_spider/bidding_spider/bidding_spider/pipelines.py`
- **改造内容**:
  - 添加 `spider_table_mapping` 配置，实现爬虫与数据表的映射
  - `jiangsu_post` 爬虫数据写入 `jiangsu_bidding_info` 表
  - 其他爬虫数据写入 `bidding_info` 表
  - `create_table_if_not_exists`: 同时创建两个表
  - `load_existing_keys`: 根据爬虫类型从对应表加载数据
  - `check_database_duplicate`: 根据爬虫类型检查对应表
  - `insert_new_item`: 根据爬虫类型插入到对应表

### 4. Flask Web 应用

#### 新增路由
- **文件**: `flask_web/app/routes/jiangsu.py`
- **路由前缀**: `/jiangsu`
- **API 列表**:
  - `GET /jiangsu/` - 江苏数据主页
  - `GET /jiangsu/api/data` - 获取江苏招标数据
  - `GET /jiangsu/api/categories` - 获取分类列表
  - `GET /jiangsu/api/sources` - 获取来源列表
  - `GET /jiangsu/api/export` - 导出 CSV
  - `GET /jiangsu/api/keyword-projects` - 获取关键词项目

#### 新增服务层
- **文件**: `flask_web/app/services/jiangsu_service.py`
- **类**: `JiangsuService`
- **方法**:
  - `get_data()` - 查询江苏招标数据
  - `get_statistics()` - 获取单日统计数据
  - `get_statistics_range()` - 获取日期范围统计数据
  - `get_categories()` - 获取分类列表
  - `get_sources()` - 获取来源列表

#### 新增模板
- **文件**: `flask_web/templates/jiangsu.html`
- **功能**:
  - 日期筛选（单日/日期范围）
  - 分类筛选
  - 来源筛选
  - 关键词搜索
  - 关键词高亮
  - CSV 导出
  - 分页显示
  - 统计卡片（总项目数、需人工查验项目、关键词数量）

#### 蓝图注册
- **文件**: `flask_web/app/__init__.py`
- **代码**:
  ```python
  from app.routes.jiangsu import jiangsu_bp
  app.register_blueprint(jiangsu_bp)
  ```

### 5. 主页导航
- **文件**: `flask_web/templates/index.html`
- **新增**: "江苏数据"功能块，链接到 `/jiangsu`

## 已更新的文档

### 1. README.md
- 功能特性：添加"江苏省"
- 爬虫列表：添加 `jiangsu_post`
- 定时任务：添加江苏爬虫 crontab 配置
- 数据库表：添加 `jiangsu_bidding_info`
- 页面功能：添加"江苏数据"页面
- API 接口：添加江苏 API 列表

### 2. SPIDER_MONITOR_GUIDE.md
- 已完成改造：添加 `jiangsu_post.py` 和 Pipeline 多表写入支持

### 3. crontab_server.txt
- 已包含江苏爬虫定时任务配置

## 访问地址

| 页面 | 路由 |
|------|------|
| 山东主页 | http://localhost:5000/ |
| 江苏数据 | http://localhost:5000/jiangsu/ |
| 监控面板 | http://localhost:5000/monitor/ |

## 验证步骤

1. **数据库验证**
   ```sql
   USE bidding_db;
   SHOW TABLES LIKE 'jiangsu%';
   ```

2. **爬虫验证**
   ```bash
   cd scrapy_spider/bidding_spider
   scrapy crawl jiangsu_post
   ```

3. **页面验证**
   - 访问 http://localhost:5000/jiangsu/
   - 检查数据展示、筛选、统计、导出功能

## 技术细节

### Pipeline 表映射
```python
self.spider_table_mapping = {
    'jiangsu_post': 'jiangsu_bidding_info',
    'sd_post': 'bidding_info',
    'jining_get': 'bidding_info',
    'taian_post': 'bidding_info',
    'jinan_post': 'bidding_info',
    'zibo_post': 'bidding_info'
}
```

### 关键词高亮
江苏页面使用与山东主页相同的关键词配置，通过 `KeywordService` 动态获取关键词列表。

### 重点关注共用
`focus_projects` 表不区分数据来源，山东和江苏的项目都可以关注到同一张表中。
