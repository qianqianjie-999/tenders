-- quick_init.sql
-- 快速初始化数据库（通过命令行执行）

-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS bidding_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 2. 使用数据库
USE bidding_db;

-- 3. 创建主表
CREATE TABLE IF NOT EXISTS bidding_info (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_name VARCHAR(500) NOT NULL,
    publish_date DATE NOT NULL,
    detail_url VARCHAR(1000) DEFAULT NULL,
    project_source VARCHAR(100) NOT NULL,
    project_category VARCHAR(50) DEFAULT NULL,
    crawl_time DATETIME NOT NULL,
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY idx_unique_project (project_name(200), publish_date, project_source(50)),
    INDEX idx_publish_date (publish_date),
    INDEX idx_project_source (project_source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;




-- 重点关注项目表
CREATE TABLE IF NOT EXISTS focus_projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(500) NOT NULL,
    publish_date DATE NOT NULL,
    project_source VARCHAR(100) NOT NULL,
    project_category VARCHAR(50),
    detail_url VARCHAR(1000),
    focus_time DATETIME NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    remark TEXT,
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_unique_focus (project_name(200), publish_date, project_source(50)),
    INDEX idx_focus_time (focus_time),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tracking_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    focus_id INT NOT NULL,
    record_content TEXT NOT NULL,
    record_time DATETIME NOT NULL,
    record_type VARCHAR(50),
    operator VARCHAR(100),
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (focus_id) REFERENCES focus_projects(id) ON DELETE CASCADE,
    INDEX idx_focus_id (focus_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


--分析标书的表

CREATE TABLE analysis_projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(500) NOT NULL,
    publish_date DATE NOT NULL,
    project_source VARCHAR(100) NOT NULL,
    project_category VARCHAR(50),
    detail_url VARCHAR(1000),

    -- 新增扩展字段
    bid_open_date DATE,                    -- 开标日期
    tenderer VARCHAR(200),                 -- 招标人
    control_price DECIMAL(15,2),           -- 招标控制价（万元）
    decision VARCHAR(20) DEFAULT 'pending', -- 分析决定：pending/投标/不投
    decision_reason TEXT,                  -- 备注原因（不投原因等）

    -- 关联和安全字段
    focus_id INT,                          -- 原关注表ID（关联用）
    access_code VARCHAR(50),               -- 独立口令（可选，如果不用全局口令）
    operator VARCHAR(100),                 -- 操作人

    import_time DATETIME NOT NULL,         -- 转入时间
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_decision (decision),
    INDEX idx_bid_date (bid_open_date),
    INDEX idx_tenderer (tenderer),
    FOREIGN KEY (focus_id) REFERENCES focus_projects(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--投标的表
CREATE TABLE bidding_projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    analysis_project_id INT,
    project_name VARCHAR(500) NOT NULL,
    project_source VARCHAR(200),
    project_category VARCHAR(100),
    publish_date DATE,
    detail_url TEXT,
    tenderer VARCHAR(200),
    control_price DECIMAL(15,2),

    -- 投标特有字段
    bid_document_creator VARCHAR(100),
    bid_document_key_points TEXT,
    bid_prices JSON,  -- 存储各家报价 [{name: '公司A', price: 1000000}, ...]
    final_status VARCHAR(20) DEFAULT 'pending', -- pending, won, lost
    summary_reason TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    operator VARCHAR(100),

    FOREIGN KEY (analysis_project_id) REFERENCES analysis_projects(id)
);


-- ==================== 爬虫监控相关表 ====================

-- 1. 爬虫运行记录表：记录每次爬虫运行的详细信息
CREATE TABLE IF NOT EXISTS spider_run_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    spider_name VARCHAR(50) NOT NULL COMMENT '爬虫名称',
    run_date DATE NOT NULL COMMENT '运行日期',
    run_index INT NOT NULL DEFAULT 1 COMMENT '当日第几次运行',
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME DEFAULT NULL COMMENT '结束时间',
    duration_seconds INT DEFAULT NULL COMMENT '运行时长(秒)',
    status VARCHAR(20) DEFAULT 'running' COMMENT '状态: running/success/failed/stopped',
    items_crawled INT DEFAULT 0 COMMENT '爬取数量',
    items_stored INT DEFAULT 0 COMMENT '实际入库数量',
    error_count INT DEFAULT 0 COMMENT '错误数',
    warning_count INT DEFAULT 0 COMMENT '警告数',
    timeout_count INT DEFAULT 0 COMMENT '超时次数',
    close_reason VARCHAR(100) DEFAULT NULL COMMENT '关闭原因',
    log_file VARCHAR(500) DEFAULT NULL COMMENT '日志文件路径',
    stats_file VARCHAR(500) DEFAULT NULL COMMENT '统计文件路径',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY idx_spider_date_run (spider_name, run_date, run_index),
    INDEX idx_run_date (run_date),
    INDEX idx_status (status),
    INDEX idx_spider_name (spider_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬虫运行记录表';


-- 2. 超时错误记录表：结构化存储超时错误日志
CREATE TABLE IF NOT EXISTS spider_timeout_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    spider_run_id INT DEFAULT NULL COMMENT '关联的运行记录ID',
    spider_name VARCHAR(50) NOT NULL COMMENT '爬虫名称',
    url TEXT NOT NULL COMMENT '超时URL',
    timeout_seconds INT DEFAULT NULL COMMENT '超时设置(秒)',
    retry_count INT DEFAULT 0 COMMENT '重试次数',
    error_message TEXT COMMENT '错误信息',
    occurred_at DATETIME NOT NULL COMMENT '发生时间',
    resolved BOOLEAN DEFAULT FALSE COMMENT '是否已解决',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_spider_name (spider_name),
    INDEX idx_occurred_at (occurred_at),
    INDEX idx_resolved (resolved),
    INDEX idx_spider_run_id (spider_run_id),
    FOREIGN KEY (spider_run_id) REFERENCES spider_run_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬虫超时错误记录表';


-- 3. 爬虫每日统计汇总表：用于快速查询每日汇总数据
CREATE TABLE IF NOT EXISTS spider_daily_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    spider_name VARCHAR(50) NOT NULL COMMENT '爬虫名称',
    stat_date DATE NOT NULL COMMENT '统计日期',
    run_count INT DEFAULT 0 COMMENT '运行次数',
    total_items_crawled INT DEFAULT 0 COMMENT '总爬取数',
    total_items_stored INT DEFAULT 0 COMMENT '总入库数',
    total_errors INT DEFAULT 0 COMMENT '总错误数',
    total_timeouts INT DEFAULT 0 COMMENT '总超时数',
    avg_duration_seconds INT DEFAULT NULL COMMENT '平均运行时长(秒)',
    success_rate DECIMAL(5,2) DEFAULT NULL COMMENT '成功率(%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY idx_spider_date (spider_name, stat_date),
    INDEX idx_stat_date (stat_date),
    INDEX idx_spider_name (spider_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬虫每日统计汇总表';