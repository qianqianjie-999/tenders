-- 添加额外索引以优化查询性能（使用IF NOT EXISTS避免重复创建）

USE bidding_db;

-- 为bidding_info表添加额外索引
ALTER TABLE bidding_info ADD INDEX IF NOT EXISTS idx_crawl_time (crawl_time);

-- 为focus_projects表添加额外索引
ALTER TABLE focus_projects ADD INDEX IF NOT EXISTS idx_project_category (project_category);

-- 为analysis_projects表添加额外索引
ALTER TABLE analysis_projects ADD INDEX IF NOT EXISTS idx_project_category (project_category);
ALTER TABLE analysis_projects ADD INDEX IF NOT EXISTS idx_control_price (control_price);

-- 为bidding_projects表添加额外索引
ALTER TABLE bidding_projects ADD INDEX IF NOT EXISTS idx_final_status (final_status);
ALTER TABLE bidding_projects ADD INDEX IF NOT EXISTS idx_project_category (project_category);

-- 为jiangsu_bidding_info表添加额外索引
ALTER TABLE jiangsu_bidding_info ADD INDEX IF NOT EXISTS idx_project_category (project_category);
ALTER TABLE jiangsu_bidding_info ADD INDEX IF NOT EXISTS idx_crawl_time (crawl_time);

-- 为spider_run_logs表添加额外索引
ALTER TABLE spider_run_logs ADD INDEX IF NOT EXISTS idx_items_crawled (items_crawled);
ALTER TABLE spider_run_logs ADD INDEX IF NOT EXISTS idx_duration_seconds (duration_seconds);

-- 为spider_timeout_logs表添加额外索引
ALTER TABLE spider_timeout_logs ADD INDEX IF NOT EXISTS idx_timeout_seconds (timeout_seconds);
ALTER TABLE spider_timeout_logs ADD INDEX IF NOT EXISTS idx_retry_count (retry_count);

-- 为spider_daily_stats表添加额外索引
ALTER TABLE spider_daily_stats ADD INDEX IF NOT EXISTS idx_total_items_crawled (total_items_crawled);
ALTER TABLE spider_daily_stats ADD INDEX IF NOT EXISTS idx_success_rate (success_rate);
