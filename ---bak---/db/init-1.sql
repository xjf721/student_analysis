-- db/init.sql
-- 课程表
CREATE TABLE IF NOT EXISTS courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_name VARCHAR(100) NOT NULL,
    semester VARCHAR(50) COMMENT '学期，如2026春',
    teacher VARCHAR(100),
    UNIQUE KEY uk_course (course_name, semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生信息表
CREATE TABLE IF NOT EXISTS students (
    student_id VARCHAR(20) PRIMARY KEY COMMENT '学号',
    name VARCHAR(50) NOT NULL,
    class_name VARCHAR(100) COMMENT '行政班',
    college VARCHAR(100) COMMENT '学院'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 知识点字典
CREATE TABLE IF NOT EXISTS knowledge_points (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kp_name VARCHAR(100) NOT NULL COMMENT '知识点名称',
    course_id INT NOT NULL,
    UNIQUE KEY uk_kp_course (kp_name, course_id),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 知识点掌握明细 (核心分析表)
CREATE TABLE IF NOT EXISTS student_kp_mastery (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    kp_id INT NOT NULL,
    completion_rate DECIMAL(5,4) COMMENT '完成率',
    self_test_correct_rate DECIMAL(5,4) COMMENT '自测正确率',
    mastery_rate DECIMAL(5,4) COMMENT '掌握率',
    record_date DATE NOT NULL COMMENT '数据日期（每次导入的日期）',
    UNIQUE KEY uk_student_kp_date (student_id, kp_id, record_date),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (kp_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学习过程数据 (对应表2，每次导入一条记录)
CREATE TABLE IF NOT EXISTS student_learning_process (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    total_classes INT COMMENT '班级开课数',
    checkin_count INT COMMENT '签到次数',
    attendance_rate DECIMAL(5,4) COMMENT '到课率',
    courseware_pages_viewed INT COMMENT '观看课件页数',
    total_courseware_pages INT COMMENT '课件总页数',
    courseware_view_rate DECIMAL(5,4) COMMENT '课件观看率',
    video_count INT COMMENT '发布视频个数',
    video_completed INT COMMENT '学生完成视频个数',
    video_completion_rate DECIMAL(5,4) COMMENT '视频完成率',
    exercise_count INT COMMENT '发布习题个数',
    exercise_submitted INT COMMENT '学生提交习题数',
    exercise_answer_rate DECIMAL(5,4) COMMENT '作答率',
    exercise_score_rate DECIMAL(5,4) COMMENT '得分率',
    post_count INT COMMENT '发帖数',
    reply_count INT COMMENT '回帖数',
    record_date DATE NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生汇总表 (对应表3)
CREATE TABLE IF NOT EXISTS student_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    overall_mastery_rate DECIMAL(5,4) COMMENT '知识点掌握率',
    knowledge_completion VARCHAR(50) COMMENT '知识点学习内容完成个数',
    completion_rate_summary DECIMAL(5,4) COMMENT '完成率',
    self_test_status VARCHAR(20) COMMENT '自测题作答情况',
    correct_status VARCHAR(20) COMMENT '正确情况',
    correct_rate DECIMAL(5,4) COMMENT '正确率',
    record_date DATE NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 头歌总成绩 (对应表6)
CREATE TABLE IF NOT EXISTS tougou_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    total_score DECIMAL(8,2) COMMENT '个人总成绩',
    experiment_scores JSON COMMENT '各实验得分（JSON 存储）',
    record_date DATE NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 头歌活跃度 (对应表5)
CREATE TABLE IF NOT EXISTS tougou_activity (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    homework_completed INT COMMENT '作业完成数',
    exam_completed INT COMMENT '试卷完成数',
    survey_completed INT COMMENT '问卷完成数',
    resource_published INT COMMENT '资源发布数',
    post_published INT COMMENT '帖子发布数',
    reply_count INT COMMENT '回帖数',
    homework_reply_count INT COMMENT '作业回复数',
    activity_score INT COMMENT '活跃度总分',
    record_date DATE NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 分析结果表 (存储薄弱点、预警等)
CREATE TABLE IF NOT EXISTS analysis_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    course_id INT NOT NULL,
    kp_id INT NOT NULL,
    weakness_level ENUM('轻微','中等','严重') COMMENT '薄弱等级',
    gap_value DECIMAL(5,4) COMMENT '与平均掌握率的差距',
    analysis_date DATE NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (kp_id) REFERENCES knowledge_points(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;