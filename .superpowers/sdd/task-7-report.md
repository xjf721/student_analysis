# Task 7 实施报告：独立班级对比页面

## 结果

- 新增 `ClassComparisonService.compare(class_ids)`，仅输出班级聚合指标并保持请求顺序。
- 新增 `GET /class-compare` 与 `GET /api/classes/compare`；不依赖也不修改 `active_class_id`。
- 页面同时支持活动/归档班级多选、数值表格与 ECharts 柱状对比图。
- 班级名称由 Jinja 自动转义；异步结果通过 `textContent` 写入表格，避免 HTML 注入。
- 预警人数统一为风险分数不低于 60 的不同学生数，Dashboard 与对比服务复用同一仓储键。
- 空班级指标统一为：出勤率 `0`、实践成绩 `0`、掌握率 `None/null`、预警人数/率 `0`。

## RED 证据

首次执行：

```text
.venv\Scripts\python.exe -m pytest tests/test_class_comparison.py -q
FFFFFFF [100%]
7 failed in 9.16s
```

所有失败均来自新路由不存在：响应为 404（对比 JSON、参数校验与页面测试均按预期失败）。

自审回归 RED：

```text
.venv\Scripts\python.exe -m pytest tests/test_class_comparison.py::test_compare_page_lists_active_and_archived_classes_without_changing_context -q
FAILED: assert page.count('class="nav-link active"') == 1
actual: 2
```

该测试准确复现“班级管理”和“班级对比”同时高亮。

## GREEN 证据

首轮功能测试：

```text
.venv\Scripts\python.exe -m pytest tests/test_class_comparison.py -q
....... [100%]
7 passed in 9.68s
```

导航回归修复：

```text
.venv\Scripts\python.exe -m pytest tests/test_class_comparison.py::test_compare_page_lists_active_and_archived_classes_without_changing_context -q
. [100%]
1 passed in 1.15s
```

全量回归：

```text
.venv\Scripts\python.exe -m pytest -q
128 passed in 108.11s (0:01:48)
```

编译与差异检查：

```text
.venv\Scripts\python.exe -m py_compile services/class_comparison.py controllers/class_controller.py controllers/dashboard_controller.py repositories/warning_repo.py tests/test_class_comparison.py
git diff --check
```

两条命令均退出码 0，无输出错误。

## 覆盖范围

- 两班指标值与输入顺序
- 重复选择、只选一个、班级不存在
- 空班级数值约定
- 多条预警记录按学生去重
- JSON 不含学生列表、学号、学生 ID 或姓名
- 与单班 Dashboard/知识统计 API 的指标一致性
- 活动与归档班级页面选项、班级名称转义
- 页面访问不改变当前班级
- 侧栏仅高亮班级对比项

## 自审结论

- 多班聚合仅由 `ClassComparisonService` 入口执行，每个仓储/分析器调用仍显式传入单一 `class_id`。
- API 在任何指标查询前完成全部班级存在性校验，避免部分结果。
- GET 路由继续受全局登录守卫保护；没有新增状态写入或 CSRF 豁免。
- 未发现未解决的功能或安全问题。
