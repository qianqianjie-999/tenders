-- =====================================================================
-- 详情页正文 + AI 分析 字段迁移
-- 2026-11-11
-- 为 3 张招标信息表新增:
--   detail_content       MEDIUMTEXT  详情页正文（去标签后）
--   ai_analysis          JSON        AI 分析结果（品类/项目类型/简介/关键词/四大类/相关性）
--   ai_analysis_status   VARCHAR(20) pending/ok/failed
--   ai_analyzed_at       DATETIME    最近一次分析时间
-- 幂等：可重复执行；重复执行会先检查列是否存在。
-- =====================================================================

USE bidding_db;

DELIMITER $$

DROP PROCEDURE IF EXISTS _add_ai_fields_to_table $$
CREATE PROCEDURE _add_ai_fields_to_table(IN tbl VARCHAR(64))
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = tbl AND column_name = 'detail_content') THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', tbl, '` ADD COLUMN detail_content MEDIUMTEXT NULL COMMENT ''详情页正文（去标签后）'' AFTER detail_url');
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = tbl AND column_name = 'ai_analysis') THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', tbl, '` ADD COLUMN ai_analysis JSON NULL COMMENT ''AI 分析结果 JSON'' AFTER detail_content');
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = tbl AND column_name = 'ai_analysis_status') THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', tbl, '` ADD COLUMN ai_analysis_status VARCHAR(20) NOT NULL DEFAULT ''pending'' COMMENT ''pending/ok/failed'' AFTER ai_analysis');
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = tbl AND column_name = 'ai_analyzed_at') THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', tbl, '` ADD COLUMN ai_analyzed_at DATETIME NULL COMMENT ''最近一次 AI 分析时间'' AFTER ai_analysis_status');
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;

    -- 索引（唯一键存在时跳过会报错；用 EXISTS 判断）
    IF NOT EXISTS (
       SELECT 1 FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = tbl AND index_name = 'idx_ai_status') THEN
        SET @sql = CONCAT('ALTER TABLE `', tbl, '` ADD INDEX idx_ai_status (ai_analysis_status, ai_analyzed_at)');
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
END$$

DELIMITER ;

CALL _add_ai_fields_to_table('bidding_info');
CALL _add_ai_fields_to_table('jiangsu_bidding_info');
CALL _add_ai_fields_to_table('zhejiang_bidding_info');

DROP PROCEDURE IF EXISTS _add_ai_fields_to_table;

-- 验证
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN ('bidding_info','jiangsu_bidding_info','zhejiang_bidding_info')
  AND column_name IN ('detail_content','ai_analysis','ai_analysis_status','ai_analyzed_at')
ORDER BY table_name, ordinal_position;
