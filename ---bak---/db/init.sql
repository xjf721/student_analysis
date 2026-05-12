-- db/init.sql
CREATE DATABASE IF NOT EXISTS student_analysis  
DEFAULT CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE student_analysis;

-- 知识点字典
CREATE TABLE IF NOT EXISTS knowledge_points (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kp_name VARCHAR(100) NOT NULL UNIQUE COMMENT '知识点名称'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生全景表（每行 = 一个学生 + 一门课程 + 一个学期 + 一次导入）
CREATE TABLE IF NOT EXISTS student_profile (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    student_id VARCHAR(20) NOT NULL COMMENT '学号',
    student_name VARCHAR(50) NOT NULL COMMENT '姓名',
    class_name VARCHAR(100) COMMENT '行政班',
    college VARCHAR(100) COMMENT '学院',
    
    course_name VARCHAR(100) NOT NULL COMMENT '课程名称',
    semester VARCHAR(50) COMMENT '学期，如 2026春',
    
    -- 学习行为指标
    attendance_rate DECIMAL(5,4) COMMENT '到课率',
    courseware_view_rate DECIMAL(5,4) COMMENT '课件观看率',
    video_completion_rate DECIMAL(5,4) COMMENT '视频完成率',
    exercise_answer_rate DECIMAL(5,4) COMMENT '习题作答率',
    exercise_score_rate DECIMAL(5,4) COMMENT '习题得分率',
    
    -- 学生汇总指标
    overall_mastery_rate DECIMAL(5,4) COMMENT '整体知识点掌握率',
    knowledge_completion_count VARCHAR(50) COMMENT '知识点完成个数',
    completion_rate DECIMAL(5,4) COMMENT '完成率',
    self_test_correct_rate DECIMAL(5,4) COMMENT '自测正确率',
    
    -- 头歌总成绩
    tougou_total_score DECIMAL(8,2) COMMENT '头歌个人总成绩',
    tougou_experiment_scores JSON COMMENT '头歌各实验得分 JSON',
    
    -- 头歌活跃度
    tougou_activity_score INT COMMENT '头歌活跃度总分',
    
    data_source VARCHAR(50) COMMENT '导入批次标识',
    record_date DATE NOT NULL COMMENT '数据记录日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_student (student_id),
    INDEX idx_class (class_name),
    INDEX idx_course (course_name, semester),
    INDEX idx_record (record_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 知识点掌握明细表（每行 = 一个学生 + 一个知识点 + 一次导入）
CREATE TABLE IF NOT EXISTS student_kp_mastery (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    student_id VARCHAR(20) NOT NULL COMMENT '学号',
    kp_name VARCHAR(100) NOT NULL COMMENT '知识点名称',
    kp_completion_rate DECIMAL(5,4) COMMENT '知识点完成率',
    kp_self_test_correct_rate DECIMAL(5,4) COMMENT '知识点自测正确率',
    kp_mastery_rate DECIMAL(5,4) COMMENT '知识点掌握率',
    
    record_date DATE NOT NULL COMMENT '数据记录日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_student_kp (student_id, kp_name),
    INDEX idx_kp_mastery (kp_name, kp_mastery_rate),
    INDEX idx_record (record_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 导入日志
CREATE TABLE IF NOT EXISTS import_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_file VARCHAR(200) COMMENT '导入的 Excel 文件名',
    record_count INT COMMENT '导入记录数',
    import_date DATE NOT NULL,
    notes TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;