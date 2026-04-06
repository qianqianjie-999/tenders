-- 为 analysis_projects 表添加标书分析情况字段
ALTER TABLE analysis_projects
ADD COLUMN analysis_content TEXT AFTER decision_reason;
