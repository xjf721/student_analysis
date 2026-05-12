# analysis.py （第一版：薄弱知识点分析）
import pymysql
import pandas as pd
from db.config import DB_CONFIG

def get_conn():
    return pymysql.connect(**DB_CONFIG)

def main():
    print("=" * 60)
    print("📊 学生学习薄弱点分析")
    print("=" * 60)

    # 1. 读取知识点掌握明细
    conn = get_conn()
    df_kp = pd.read_sql("""
        SELECT student_id, kp_name, kp_mastery_rate
        FROM student_kp_mastery
        WHERE record_date = (SELECT MAX(record_date) FROM student_kp_mastery)
    """, conn)

    # 2. 读取学生信息（学号→姓名映射）
    df_stu = pd.read_sql("""
        SELECT DISTINCT student_id, student_name
        FROM student_profile
        WHERE record_date = (SELECT MAX(record_date) FROM student_profile)
    """, conn)
    conn.close()

    # 合并姓名
    df = df_kp.merge(df_stu, on='student_id', how='left')

    # 3. 计算每个知识点的全班平均掌握率
    kp_avg = df.groupby('kp_name')['kp_mastery_rate'].mean().reset_index()
    kp_avg.columns = ['kp_name', 'avg_mastery_rate']
    print(f"\n📚 共 {len(kp_avg)} 个知识点有数据")

    # 4. 合并平均值，计算差距
    df = df.merge(kp_avg, on='kp_name', how='left')
    df['gap'] = df['kp_mastery_rate'] - df['avg_mastery_rate']

    # 5. 找出薄弱知识点（低于平均且差距超过 5%）
    threshold = -0.05  # 可调整
    weak = df[df['gap'] < threshold].copy()
    weak.sort_values(['student_name', 'gap'], inplace=True)

    # 6. 个人薄弱点报告
    print("\n" + "=" * 60)
    print("📋 个人薄弱知识点报告")
    print("=" * 60)

    for name, group in weak.groupby('student_name'):
        print(f"\n【{name}】")
        for _, row in group.iterrows():
            gap_pct = row['gap'] * 100
            level = '🔴严重' if gap_pct < -20 else ('🟡中等' if gap_pct < -10 else '🟢轻微')
            print(f"  {level} {row['kp_name']}: "
                  f"掌握率 {row['kp_mastery_rate']:.1%}, "
                  f"班级平均 {row['avg_mastery_rate']:.1%}, "
                  f"差距 {gap_pct:+.1f}%")

    # 7. 全班薄弱点汇总
    print("\n" + "=" * 60)
    print("📊 全班薄弱知识点汇总")
    print("=" * 60)

    kp_summary = weak.groupby('kp_name').agg(
        weak_student_count=('student_id', 'nunique'),
        avg_gap=('gap', 'mean')
    ).reset_index()
    kp_summary['avg_gap_pct'] = kp_summary['avg_gap'] * 100
    kp_summary.sort_values('weak_student_count', ascending=False, inplace=True)

    print(f"\n{'知识点':<30} {'薄弱人数':>6} {'平均差距':>10}")
    print("-" * 48)
    for _, row in kp_summary.iterrows():
        print(f"{row['kp_name']:<30} {row['weak_student_count']:>6}人 {row['avg_gap_pct']:>+9.1f}%")

if __name__ == "__main__":
    main()