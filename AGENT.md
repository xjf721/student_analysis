# AGENT.md

# 教学过程智能分析与预警平台

## 一、项目目标

本项目旨在构建一个：

# 面向教师的教学过程智能分析与预警平台

系统核心目标：

* 汇聚多平台教学数据
* 建立学生学习画像
* 自动识别学习风险
* 辅助教师精准教学
* 支持后续 AI 分析扩展

系统不是传统成绩管理系统。

系统核心定位：

```text
教学行为分析 + 知识掌握分析 + 风险预警
```

---

# 二、当前数据来源

系统当前已接入以下数据：

| 数据源       | 类型    | 内容             |
| --------- | ----- | -------------- |
| 雨课堂学习过程数据 | Excel | 到课率、视频完成率、作答率等 |
| 雨课堂学生汇总表  | Excel | 课堂总体学习情况       |
| 头歌总成绩     | Excel | 实验总成绩          |
| 头歌活跃度     | Excel | 学习活跃情况         |
| 头歌作业成绩表   | Excel | 实验作业明细         |

后续可能需要支持：

* MOOC
* 腾讯课堂

等等，因此：

# 导入系统必须插件化设计

---

# 三、核心开发原则

# 1. 页面不负责复杂计算

禁止：

```text
页面访问时实时计算复杂分析
```

正确流程：

```text
Excel导入
    ↓
数据清洗
    ↓
分析引擎计算
    ↓
写入分析结果表
    ↓
页面只负责读取结果
```

---

# 2. 所有分析逻辑必须进入 Service 层

禁止：

```python
@app.route()
def xxx():
    # 在路由中写复杂分析
```

正确方式：

```python
result = behavior_analyzer.calculate()
```

---


# 3. 数据导入必须解耦

禁止：

```python
if type == '雨课堂':
```

必须采用：

```python
class BaseImporter:
```

插件化结构。

---

## 3.1 导入模块常见陷阱（经验总结）

以下是在实际开发中遇到的典型问题，后续开发必须避免。

### 陷阱1：`secure_filename()` 会吃掉中文

`werkzeug.utils.secure_filename()` 会删除所有非 ASCII 字符（包括中文），导致：

```
原文件名：2026春-24大数据管理与应用-雨课堂-学生汇总表.xls
处理后：  2026-241--.xls
```

**正确做法**：

- 用 `secure_filename()` 处理后的文件名保存到磁盘
- 用 `original_filename`（保留中文）传给导入器做去重判断、班级名提取等逻辑
- `BaseImporter.__init__` 应支持 `display_filename` 参数

---

### 陷阱2：DataFrame 重复列名导致 Series 歧义错误

当 DataFrame 存在重复列名时，`row[col]` 返回 Series 而非标量值，`pd.isna()` 等判断会报：

```
The truth value of a Series is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all().
```

**产生重复列名的典型场景**：

- `auto_map_columns()` 将多个不同列名映射到同一个标准名（例："学生到课率" 和 "到课率" 都映射成 "到课率"）
- 多行表头处理时主表头和子表头产生重复列名

**预防措施**：

1. `auto_map_columns()` 必须检测重复映射，第一个保留原名，后续加 `_N` 后缀
2. 设置列名前先调去重函数 `_make_unique_columns()`
3. 解析数据时用安全辅助函数 `get_scalar()` 提取列值（先检查列是否存在，再确保返回标量）
4. 不依赖 `row.get()` 的默认值参数

---

### 陷阱3：`.xls` 扩展名不等于 xlrd 可读格式

文件扩展名 `.xls` 但实际可能是 `.xlsx` 格式，`xlrd >= 2.0` 会报：
```
XLRDError: Excel xlsx file; not supported
```

反之，真正的 `.xls` 文件 `openpyxl` 也不支持：
```
File contains no valid workbook part
```

**正确做法**：

- 统一使用 `read_excel_smart()` 函数，按扩展名选主引擎，失败自动降级
- `pd.ExcelFile()` 也不能硬编码引擎，必须双引擎降级尝试
- 不要依赖文件扩展名判断真实的 Excel 格式

---

### 陷阱4：`header=None` 与列名校验冲突

部分导入器（如知识图谱明细表）用 `header=None` 读取文件，DataFrame 列名变成整数 `[0,1,2,...]`。

基类 `validate()` 检查 `get_expected_columns()` 返回的 `['学号', '姓名']` 必然失败。

**正确做法**：

- 此类导入器重写 `validate()`，跳过列名校验
- `get_expected_columns()` 返回空列表

---

### 陷阱5：哨兵值区分"未传参"和"传了 None"

```python
def func(arg=None):  # 无法区分"调用者不传参"和"调用者传 None"
```

当需要 `header=None` 表示"不指定表头"时，与默认值 `None` 冲突。

**正确做法**：

```python
_UNSET = object()  # 模块级哨兵

def read_excel_smart(file_path, header=_UNSET):
    kwargs = {}
    if header is not _UNSET:
        kwargs['header'] = header
```

---

### 陷阱6：多 Sheet 文件只读第一个 Sheet

头歌作业成绩表 14 个 Sheet，每个 Sheet 对应一门作业。继承 `BaseImporter._read_file()` 只会读到第一个 Sheet。

**正确做法**：

- 实现 `_read_all_sheets()` 遍历所有 Sheet
- 按学号跨 Sheet 汇总数据

---

### 陷阱7：列名模糊匹配过于激进

使用"包含关系"模糊匹配时，无关列被错误映射：

| 原始列名 | 错误映射 | 原因 |
|---------|---------|------|
| 学生签到次数 | 姓名 | 包含"学生" |
| 平均得分率 | 得分率_1 | 包含"得分率" |

**正确做法**：

- 禁用包含关系的模糊匹配
- 仅使用：规范名精确匹配 + 别名精确匹配
- 通过 `column_mapping.json` 维护所有可映射的别名

---

### 陷阱8：数据库被删除后启动崩溃

**正确做法**：

- `models/base.py` 的 `init_db()` 前调用 `ensure_database_exists()` 自动创建库
- 提供 `init_database.py` 独立脚本支持手动初始化（含 `--reset` 参数）

---


# 4. 所有分析结果必须持久化

禁止：

```text
每次页面重新计算热力图
```

必须：

```text
分析后写入数据库
```

---

# 5. 数据模型优先于页面

开发优先级：

```text
数据库模型
→ 分析逻辑
→ API
→ 页面
```

不是先做页面。

---

# 四、技术栈（固定）

| 模块         | 技术                    |
| ---------- | --------------------- |
| 后端         | Flask                 |
| ORM        | SQLAlchemy            |
| 数据分析       | Pandas                |
| 前端         | Bootstrap5 + AdminLTE |
| 图表         | ECharts               |
| 数据库        | MySQL8                |
| 文件上传       | Flask Upload          |
| 缓存（第二阶段）   | Redis                 |
| 后台任务（第二阶段） | Celery/APScheduler    |
| 运行环境         | WSL                 |

---

# 五、推荐项目结构（必须遵循）

```text
student_analysis/
├── app.py
├── config.py
├── requirements.txt
│
├── controllers/
│   ├── dashboard_controller.py
│   ├── student_controller.py
│   ├── knowledge_controller.py
│   ├── class_controller.py
│   ├── warning_controller.py
│   └── import_controller.py
│
├── services/
│   ├── analysis/
│   │   ├── behavior_analyzer.py
│   │   ├── knowledge_analyzer.py
│   │   ├── practice_analyzer.py
│   │   ├── warning_engine.py
│   │   └── class_analyzer.py
│   │
│   ├── importers/
│   │   ├── base_importer.py
│   │   ├── rainclass_importer.py
│   │   ├── educoder_importer.py
│   │   └── parser_utils.py
│   │
│   └── cache/
│       └── analysis_cache.py
│
├── repositories/
│   ├── student_repo.py
│   ├── behavior_repo.py
│   ├── knowledge_repo.py
│   └── warning_repo.py
│
├── models/
│   ├── student.py
│   ├── course.py
│   ├── class_model.py
│   ├── behavior.py
│   ├── knowledge.py
│   ├── warning.py
│   └── snapshot.py
│
├── templates/
├── static/
├── uploads/
├── logs/
└── tasks/
```

---

# 六、数据库设计规范

# 1. student

学生基础信息。

字段：

```text
id
student_no
name
class_id
major
created_at
```

---

# 2. class_info

班级信息。

字段：

```text
id
class_name
teacher_name
term
```

---

# 3. student_behavior（核心）

学习行为数据。

来源：雨课堂。

字段：

```text
student_id
attendance_rate
ppt_view_rate
video_finish_rate
exercise_submit_rate
exercise_score_rate
discussion_count
reply_count
updated_at
```

说明：

所有行为数据统一存入此表。

禁止字段散落在多个表中。

---

# 4. student_practice

实践能力数据。

来源：头歌。

字段：

```text
student_id
total_score
activity_score
assignment_count
avg_experiment_score
high_retry_count
last_submit_time
```

---

# 5. student_knowledge_mastery（系统核心）

知识点掌握情况。

字段：

```text
student_id
knowledge_name
mastery_rate
mastery_level
source
updated_at
```

说明：

后续：

* 热力图
* AI分析
* 风险分析
* 知识点排行

全部基于此表。

---

# 6. warning_record

风险预警记录。

字段：

```text
id
student_id
warning_type
warning_level
warning_score
warning_reason
created_at
```

---

# 7. import_record

导入日志。

字段：

```text
filename
import_type
import_status
success_count
failed_count
created_at
```

作用：

* 防止重复导入
* 支持错误追踪
* 支持回滚

---

# 七、导入模块规范

# 必须使用插件化结构

## BaseImporter

```python
class BaseImporter:

    def validate(self):
        pass

    def clean(self):
        pass

    def parse(self):
        pass

    def save(self):
        pass
```

---

# RainClassImporter

负责：

* 到课率
* 视频完成率
* 作答率
* 得分率

---

# EducoderImporter

负责：

* 总成绩
* 活跃度
* 作业行为分析

---

# 数据校验必须实现

必须校验：

| 校验项    |
| ------ |
| 缺失字段   |
| 学号为空   |
| 重复导入   |
| 编码错误   |
| 文件格式错误 |
| 重复学生   |

导入失败必须返回明确错误信息。

---

# 八、分析引擎规范

# 1. behavior_analyzer.py

负责：

* 到课分析
* 视频学习分析
* 活跃度分析
* 课堂参与分析

输出：

```json
{
  "behavior_score": 85,
  "attendance_level": "高"
}
```

---

# 2. knowledge_analyzer.py

负责：

* 知识点掌握率
* 薄弱点识别
* 班级平均对比
* 热力图数据生成

核心输出：

```text
学生 × 知识点矩阵
```

---

# 3. practice_analyzer.py

负责：

* 实验能力分析
* 提交行为分析
* 高频失败分析
* 实践能力评分

---

# 4. warning_engine.py（核心）

必须配置化。

禁止写死。

---

# 推荐风险规则

| 条件          | 风险等级 |
| ----------- | ---- |
| 到课率 < 60%   | 一级   |
| 视频完成率 < 40% | 一级   |
| 实验平均分 < 50  | 一级   |
| 理论实践差值 > 30 | 二级   |
| 连续低活跃       | 二级   |

---

# 风险指数（必须实现）

输出：

```text
Risk Score
```

规则：

| 分值     | 等级 |
| ------ | -- |
| 0-30   | 正常 |
| 30-60  | 关注 |
| 60-80  | 预警 |
| 80-100 | 高危 |

---

# 九、页面规范

# 1. Dashboard 首页

路径：

```text
/
```

必须包含：

## 指标卡片

* 总学生数
* 平均到课率
* 平均实验成绩
* 风险学生数
* 薄弱知识点数

---

## 图表区域

### 班级画像雷达图

指标：

* 到课率
* 视频完成率
* 活跃度
* 作答率
* 实验成绩

---

### 风险学生排行

---

### 知识点热力图

---

# 2. 学生画像页

路径：

```text
/student/<id>
```

必须包含：

* 基础信息
* 学习行为雷达图
* 理论 vs 实践对比图
* 薄弱知识点列表
* 风险原因分析

---

# 3. 知识点分析页

路径：

```text
/knowledge
```

必须包含：

* 知识点掌握率排行
* 热力图
* 学生排名
* 风险学生列表

---

# 4. 班级对比页

路径：

```text
/class-compare
```

必须支持：

* 平均到课率对比
* 平均掌握率对比
* 平均实验成绩对比
* 风险学生占比对比

---

# 5. 数据导入页

路径：

```text
/import
```

必须支持：

* 上传文件
* 自动识别类型
* 数据校验
* 导入日志
* 一键重新分析

---

# 十、性能规范（必须遵守）

# 1. 页面禁止实时复杂分析

必须：

```text
导入后后台分析
```

页面只读取结果。

---

# 2. 热力图禁止一次加载全量数据

必须：

* 支持分页
* 支持班级筛选
* 支持 TopN

否则 ECharts 会卡顿。

---

# 3. SQL 禁止复杂嵌套查询

复杂分析必须：

```text
提前计算后存储
```

---

# 十一、代码规范

# Python规范

* 必须使用类型注解
* 必须写 docstring
* 不允许超长函数
* 单函数不超过 150 行
* 分析逻辑必须拆分

---

# 命名规范

## 文件名

```text
snake_case
```

## 类名

```text
PascalCase
```

## 数据库字段

```text
snake_case
```

---

# 日志规范

必须记录：

* 导入日志
* 分析日志
* 错误日志
* SQL错误

日志文件：

```text
logs/system.log
```

---

# 十二、阶段开发计划

# 第一阶段（MVP）

目标：

# 做出真正可运行版本

功能：

* Excel导入
* Dashboard
* 学生画像
* 知识点热力图
* 风险预警

禁止增加：

* AI
* 实时分析
* 前后端分离
* 多角色权限

---

# 第二阶段

增加：

* Redis缓存
* 趋势分析
* 历史快照
* PDF报告
* 多班级分析

---

# 第三阶段

增加：

* AI教学建议
* 聚类分析
* 风险预测
* 自动周报
* 大模型分析

---

# 十三、未来扩展方向

后续系统必须支持：

# 1. AI教学建议

例如：

```text
该学生实验能力较弱，建议增加链表与栈相关训练。
```

---

# 2. 学生学习分群

例如：

| 类型     |
| ------ |
| 高参与高成绩 |
| 高参与低成绩 |
| 低参与高成绩 |
| 低参与低成绩 |

---

# 3. 理论 vs 实践偏差分析

系统核心亮点。

输出：

| 类型     |
| ------ |
| 理论强实践弱 |
| 理论弱实践强 |
| 双强     |
| 双弱     |

---

# 十四、最终目标

系统最终定位：

# 教学过程智能分析与预警平台

核心价值：

```text
行为分析
+ 知识掌握分析
+ 风险识别
+ 教学决策支持
```

而不是普通成绩管理系统。

---

# 十五、开发优先级（必须遵循）

开发顺序：

```text
1. 数据库模型
2. 数据导入
3. 分析引擎
4. 分析结果表
5. Dashboard
6. 学生画像
7. 热力图
8. 风险预警
9. 趋势分析
10. AI功能
```

禁止：

```text
先堆页面再补分析逻辑
```

系统核心永远是：

# 分析引擎
