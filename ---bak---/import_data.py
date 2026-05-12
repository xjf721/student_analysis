# import_data.py （完整版：六表合并导入）
import pandas as pd
import pymysql
import sys
import json
from datetime import date
from db.config import DB_CONFIG

# 文件路径
EXCEL_雨课堂_过程 = "2026春-24大数据管理与应用(数据保障)(青年1班)-雨课堂-班级数据统计与学习过程数据.xlsx"
EXCEL_雨课堂_汇总 = "2026春-24大数据管理与应用(数据保障)(青年1班)-雨课堂-学生汇总表.xls"
EXCEL_雨课堂_知识图谱 = "2026春-24大数据管理与应用(数据保障)(青年1班)-雨课堂-知识图谱学习数据明细表.xls"
EXCEL_头歌_活跃度 = "程序设计与数据结构(二)_(数据结构_C++描述）2026春_头歌_活跃度.xlsx"
EXCEL_头歌_总成绩 = "程序设计与数据结构(二)_(数据结构_C++描述）2026春_头歌_总成绩.xlsx"
EXCEL_头歌_作业 = "程序设计与数据结构(二)_(数据结构_C++描述）2026春_头歌_作业成绩表.xlsx"

TODAY = date.today().isoformat()

def get_conn():
    return pymysql.connect(**DB_CONFIG)

# ==================== 雨课堂：学习过程数据 ====================
def import_learning_process():
    print("\n📊 [1/6] 学习过程数据...")
    df_raw = pd.read_excel(EXCEL_雨课堂_过程, sheet_name="学习过程数据", header=None)
    mask = pd.to_numeric(df_raw.iloc[:, 2], errors='coerce').notna()
    df_raw = df_raw.loc[mask].copy()

    df = pd.DataFrame()
    df['学号']   = df_raw.iloc[:, 2].astype(str).str.strip()
    df['姓名']   = df_raw.iloc[:, 1].astype(str).str.strip()
    df['所属行政班'] = df_raw.iloc[:, 3].astype(str).str.strip()
    df['所属学院']  = df_raw.iloc[:, 4].astype(str).str.strip()
    df['到课率']   = pd.to_numeric(df_raw.iloc[:, 7], errors='coerce')
    df['课件观看率'] = pd.to_numeric(df_raw.iloc[:, 11], errors='coerce')
    df['学生视频完成率'] = pd.to_numeric(df_raw.iloc[:, 14], errors='coerce')
    df['学生作答率']  = pd.to_numeric(df_raw.iloc[:, 17], errors='coerce')
    df['学生得分率']  = pd.to_numeric(df_raw.iloc[:, 18], errors='coerce')

    conn = get_conn()
    cursor = conn.cursor()
    sql = """
    INSERT INTO student_profile (
        student_id, student_name, class_name, college,
        course_name, semester,
        attendance_rate, courseware_view_rate, video_completion_rate,
        exercise_answer_rate, exercise_score_rate,
        overall_mastery_rate, knowledge_completion_count,
        completion_rate, self_test_correct_rate,
        tougou_total_score, tougou_experiment_scores,
        tougou_activity_score,
        data_source, record_date
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        NULL, NULL, NULL, NULL,
        NULL, NULL, NULL,
        '雨课堂', %s
    )
    """
    inserted = 0
    for _, row in df.iterrows():
        try:
            cursor.execute(sql, (
                row['学号'], row['姓名'], row['所属行政班'], row['所属学院'],
                "程序设计与数据结构(二)", "2026春",
                float(row['到课率']), float(row['课件观看率']),
                float(row['学生视频完成率']), float(row['学生作答率']),
                float(row['学生得分率']), TODAY
            ))
            inserted += 1
        except Exception as e:
            print(f"  ⚠ {row['姓名']}: {e}")
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 导入 {inserted} 条")

# ==================== 雨课堂：学生汇总 ====================
def import_student_summary():
    print("\n📊 [2/6] 学生汇总...")
    df = pd.read_excel(EXCEL_雨课堂_汇总, sheet_name="数据结构")
    df = df.rename(columns={
        df.columns[0]: '姓名', df.columns[1]: '学号',
        df.columns[2]: '知识点掌握率', df.columns[3]: '完成情况',
        df.columns[4]: '完成率', df.columns[5]: '自测作答情况',
        df.columns[6]: '正确情况', df.columns[7]: '正确率'
    })
    df = df[pd.to_numeric(df['学号'], errors='coerce').notna()].copy()

    conn = get_conn(); cursor = conn.cursor()
    updated = 0
    for _, row in df.iterrows():
        mastery = float(str(row['知识点掌握率']).replace('%',''))/100
        comp_rate = float(str(row['完成率']).replace('%',''))/100 if pd.notna(row['完成率']) else None
        corr_rate = float(str(row['正确率']).replace('%',''))/100 if pd.notna(row['正确率']) else None
        cursor.execute("""
            UPDATE student_profile SET
                overall_mastery_rate=%s, knowledge_completion_count=%s,
                completion_rate=%s, self_test_correct_rate=%s
            WHERE student_id=%s AND course_name='程序设计与数据结构(二)'
              AND semester='2026春' AND record_date=%s
        """, (mastery, row['完成情况'], comp_rate, corr_rate, row['学号'], TODAY))
        if cursor.rowcount > 0: updated += 1
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 更新 {updated} 条")

# ==================== 雨课堂：知识图谱明细 ====================
def import_knowledge_mastery():
    print("\n📊 [3/6] 知识图谱明细...")
    df_raw = pd.read_excel(EXCEL_雨课堂_知识图谱, sheet_name="数据结构", header=None)
    header = df_raw.iloc[0, :]
    # 构建知识点列索引
    kp_cols = []
    for idx in range(2, len(header)):
        if pd.notna(header.iloc[idx]) and 'Unnamed' not in str(header.iloc[idx]):
            name = str(header.iloc[idx]).strip()
            if name not in ['完成率','自测习题正确率','掌握率','']:
                kp_cols.append((idx, name))
    df_data = df_raw.iloc[2:, :]
    df_data = df_data[pd.to_numeric(df_data.iloc[:, 0], errors='coerce').notna()]

    conn = get_conn(); cursor = conn.cursor()
    for _, kp_name in kp_cols:
        cursor.execute("INSERT IGNORE INTO knowledge_points (kp_name) VALUES (%s)", (kp_name,))
    inserted = 0
    for _, row in df_data.iterrows():
        student_id = str(row.iloc[0]).strip()
        if not student_id.isdigit(): continue
        for col_idx, kp_name in kp_cols:
            vals = [row.iloc[col_idx], row.iloc[col_idx+1], row.iloc[col_idx+2]]
            parsed = []
            for v in vals:
                if pd.isna(v) or str(v).strip()=='': parsed.append(None)
                else: parsed.append(float(str(v).replace('%',''))/100)
            if all(x is None for x in parsed): continue
            cursor.execute("""
                INSERT INTO student_kp_mastery 
                (student_id, kp_name, kp_completion_rate, kp_self_test_correct_rate, kp_mastery_rate, record_date)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    kp_completion_rate=VALUES(kp_completion_rate),
                    kp_self_test_correct_rate=VALUES(kp_self_test_correct_rate),
                    kp_mastery_rate=VALUES(kp_mastery_rate)
            """, (student_id, kp_name, parsed[0], parsed[1], parsed[2], TODAY))
            inserted += 1
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 导入/更新 {inserted} 条")

# ==================== 头歌：活跃度 ====================
def import_tougou_activity():
    print("\n📊 [4/6] 头歌活跃度...")
    df = pd.read_excel(EXCEL_头歌_活跃度, sheet_name="课堂活跃度统计")
    df = df[pd.to_numeric(df['学号'], errors='coerce').notna()]
    conn = get_conn(); cursor = conn.cursor()
    updated = 0
    for _, row in df.iterrows():
        cursor.execute("""
            UPDATE student_profile SET tougou_activity_score=%s
            WHERE student_id=%s AND course_name='程序设计与数据结构(二)'
              AND semester='2026春' AND record_date=%s
        """, (int(row['活跃度']), str(row['学号']).strip(), TODAY))
        if cursor.rowcount > 0: updated += 1
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 更新 {updated} 条")

# ==================== 头歌：总成绩 ====================
def import_tougou_scores():
    print("\n📊 [5/6] 头歌总成绩...")
    df_raw = pd.read_excel(EXCEL_头歌_总成绩, sheet_name="学生总成绩", header=None)
    header_exp = df_raw.iloc[1, :]
    df_data = df_raw.iloc[2:, :]
    df_data = df_data[pd.to_numeric(df_data.iloc[:, 4], errors='coerce').notna()]

    conn = get_conn(); cursor = conn.cursor()
    updated = 0
    for _, row in df_data.iterrows():
        sid = str(int(float(row.iloc[4])))
        total = float(row.iloc[7]) if pd.notna(row.iloc[7]) else None
        exp_dict = {}
        for ci in range(9, len(row)):
            name = str(header_exp.iloc[ci]) if pd.notna(header_exp.iloc[ci]) else f"E{ci-8}"
            exp_dict[name] = float(row.iloc[ci]) if pd.notna(row.iloc[ci]) else 0
        cursor.execute("""
            UPDATE student_profile SET tougou_total_score=%s, tougou_experiment_scores=%s
            WHERE student_id=%s AND course_name='程序设计与数据结构(二)'
              AND semester='2026春' AND record_date=%s
        """, (total, json.dumps(exp_dict, ensure_ascii=False), sid, TODAY))
        if cursor.rowcount > 0: updated += 1
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 更新 {updated} 条")

# ==================== 头歌：作业明细 ====================
def import_tougou_homework():
    print("\n📊 [6/6] 头歌作业明细...")
    xls = pd.ExcelFile(EXCEL_头歌_作业)
    sheets = [s for s in xls.sheet_names if s.startswith('1.') or s.startswith('2.') or
              s.startswith('3.') or s.startswith('4.') or s.startswith('5.')]
    
    conn = get_conn(); cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tougou_homework_detail (
        id INT AUTO_INCREMENT PRIMARY KEY,
        student_id VARCHAR(20), homework_name VARCHAR(200),
        submit_status VARCHAR(50), score DECIMAL(5,2),
        duration VARCHAR(50), eval_count INT, record_date DATE,
        INDEX idx_sh (student_id, homework_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    total = 0
    for s in sheets:
        df = pd.read_excel(EXCEL_头歌_作业, sheet_name=s)
        df = df[pd.to_numeric(df['学号'], errors='coerce').notna()]
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO tougou_homework_detail
                (student_id, homework_name, submit_status, score, duration, eval_count, record_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE score=VALUES(score)
            """, (
                str(row['学号']).strip(), s[:200], row.get('提交状态'),
                float(row['最终成绩']) if pd.notna(row.get('最终成绩')) else None,
                row.get('本实训总耗时'), int(row['总评测次数']) if pd.notna(row.get('总评测次数')) else None,
                TODAY
            ))
            total += 1
    conn.commit(); cursor.close(); conn.close()
    print(f"  ✅ 导入 {total} 条作业明细")

# ==================== 主流程 ====================
def main():
    print("="*60)
    print("📥 六表联合数据导入")
    print("="*60)
    try:
        import_learning_process()
        import_student_summary()
        import_knowledge_mastery()
        import_tougou_activity()
        import_tougou_scores()
        import_tougou_homework()
        conn = get_conn(); cursor = conn.cursor()
        cursor.execute("INSERT INTO import_log (source_file, record_count, import_date, notes) VALUES (%s,%s,%s,%s)",
                       ("全量六表", 6, TODAY, "六张表一次性导入"))
        conn.commit(); cursor.close(); conn.close()
        print("\n🎉 全部导入完成！")
    except Exception as e:
        print(f"\n❌ 导入失败：{e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()