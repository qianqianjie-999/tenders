-- ==============================================
-- 修复 spider_timeout_logs 表缺失的 response_status 列
-- 创建时间: 2026-04-28
-- ==============================================

USE bidding_db;

-- 直接添加列，如果已存在则忽略错误
-- 使用 ALTER IGNORE TABLE 在较新版本的MariaDB中不支持
-- 改用简单的ALTER TABLE，重复执行时会报错但不影响数据
ALTER TABLE spider_timeout_logs 
ADD COLUMN IF NOT EXISTS response_status INT(11) NULL AFTER warning_type;

-- 验证修复结果
SELECT '修复完成，检查表结构:' AS message;
DESCRIBE spider_timeout_logs;