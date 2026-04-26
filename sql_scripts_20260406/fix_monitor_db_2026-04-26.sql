-- 修复监控数据库表结构
-- 为 spider_timeout_logs 表添加 warning_type 字段

-- 1. 为 spider_timeout_logs 表添加 warning_type 字段
ALTER TABLE spider_timeout_logs 
ADD COLUMN warning_type VARCHAR(50) DEFAULT NULL COMMENT '接口警告类型';

-- 2. 为 warning_type 字段添加索引，提高查询性能
CREATE INDEX idx_spider_timeout_warning_type ON spider_timeout_logs(warning_type);

-- 3. 为 spider_name 和 warning_type 添加组合索引，优化按爬虫查询接口警告
CREATE INDEX idx_spider_name_warning_type ON spider_timeout_logs(spider_name, warning_type);

-- 4. 为 occurred_at 和 warning_type 添加组合索引，优化时间范围查询
CREATE INDEX idx_occurred_at_warning_type ON spider_timeout_logs(occurred_at, warning_type);

-- 5. 查看修改后的表结构
DESCRIBE spider_timeout_logs;