# 项目开发 TODO 清单

> 最后更新：2026-05-11

---

## ✅ 已完成

### P0-3：灵活导入配置
- [x] 创建 `config/column_mapping.json` 配置文件
- [x] 在 `parser_utils.py` 添加 `match_column_name()` 和 `auto_map_columns()` 函数
- [x] 所有导入器已更新使用自动列名映射
- [x] 测试验证通过（21个列名匹配测试）

### P0-1：自动创建班级并关联学生
- [x] 在 `parser_utils.py` 添加 `extract_class_info_from_filename()` 函数
- [x] 在 `base_importer.py` 添加 `_get_or_create_class()` 方法
- [x] 所有导入器已更新自动关联班级
- [x] 测试验证通过（4个文件名提取测试）

### 数据库自动创建
- [x] 修改 `models/base.py` 添加 `ensure_database_exists()` 函数
- [x] 创建 `init_database.py` 独立初始化脚本
- [x] 支持 `--reset` 和 `--tables-only` 参数

### Bug 修复
- [x] 修复 `base_importer.py` 缺少 `Optional` 导入
- [x] 修复 RainClassImporter 的 Series 歧义错误

---

## 📋 待办任务

### P0 - 高优先级（数据正确性问题）

#### P0-2：风险预警保留历史记录
**问题**：`warning_engine.py` 每次分析时 `delete()` 所有旧预警，无法追踪趋势。
**影响**：无法查看学生预警变化趋势。
**方案**：
1. 修改 `WarningRecord` 模型，添加 `analyzed_at` 时间戳字段
2. 改为更新或创建新记录，保留历史
3. 添加查询历史预警的接口

---

### P1 - 中优先级（性能问题）

#### P1-4：优化分析引擎（N+1查询问题）
**问题**：`behavior_analyzer.py` 逐个学生查询处理，36个学生 = 36次数据库查询。
**影响**：数据量大时分析缓慢。
**方案**：
1. 批量查询所有学生行为数据
2. 在内存中处理计算逻辑
3. 批量更新数据库

#### P1-5：优化热力图查询
**问题**：`knowledge_analyzer.py` 嵌套循环（学生×知识点），每个单元格单独查询。
**影响**：50学生×20知识点 = 1000次查询。
**方案**：
1. 使用SQL聚合一次性获取数据
2. 使用 `JOIN` 和 `GROUP BY` 优化查询

#### P1-6：列表查询分页
**问题**：学生列表、预警列表等使用 `.all()` 或 `.limit()` 但无分页参数。
**影响**：数据量大时前端加载慢。
**方案**：
1. 添加分页支持（offset/limit 或 page/per_page）
2. 更新API返回分页元数据

---

### P2 - 低优先级（设计问题）

#### P2-7：统一评分权重配置
**问题**：评分权重在 `behavior.py` 和 `behavior_analyzer.py` 中重复定义。
**影响**：修改权重需改多处，易遗漏。
**方案**：
1. 统一提取到配置文件（如 `config/scoring_rules.json`）
2. 模型和分析器都从配置读取权重

#### P2-8：导入回滚机制
**问题**：导入失败时部分数据可能已写入数据库。
**影响**：数据不一致。
**方案**：
1. 使用事务包裹整个导入流程
2. 失败时回滚所有更改
3. 记录导入日志便于追踪

#### P2-9：完善日志记录
**问题**：缺少导入、分析、预警操作的详细日志。
**影响**：问题排查困难。
**方案**：
1. 添加结构化日志记录
2. 记录操作时间、用户、结果等信息
3. 支持日志查询和导出

---

### P3 - 其他

#### P3-10：移除敏感信息
**问题**：`config.py` 包含数据库密码硬编码。
**影响**：安全风险。
**方案**：
1. 使用环境变量或 `.env` 文件
2. 添加 `.env.example` 模板
3. 更新 `.gitignore` 排除 `.env`

---

## 相关文件索引

| 文件 | 说明 |
|------|------|
| `config/column_mapping.json` | 列名映射配置 |
| `services/importers/parser_utils.py` | 解析工具函数 |
| `services/importers/base_importer.py` | 导入器基类 |
| `services/importers/rainclass_importer.py` | 雨课堂导入器 |
| `services/importers/educoder_importer.py` | 头歌导入器 |
| `services/analysis/warning_engine.py` | 风险预警引擎 |
| `services/analysis/behavior_analyzer.py` | 行为分析器 |
| `services/analysis/knowledge_analyzer.py` | 知识点分析器 |
| `models/base.py` | 数据库基础模型 |
| `models/warning.py` | 预警记录模型 |
| `init_database.py` | 数据库初始化脚本 |
