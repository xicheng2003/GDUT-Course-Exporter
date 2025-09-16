# iCalendar 增量更新机制说明 (UID / DTSTAMP / LAST-MODIFIED / SEQUENCE / 状态持久化)

本项目的 `core/ical_generator.py` 已实现对 iCalendar 事件增量更新的支持，使订阅端（Apple / Google / Outlook 等）可以更准确地识别哪些课程是新增、哪些被更新、哪些保持不变，避免每次全量刷新。

## 目标
1. 为每条课程事件生成稳定唯一标识 (UID)，保证重复生成时能覆盖而不是新建。
2. 正确维护以下标准字段：
   - `UID`：事件唯一身份。
   - `DTSTAMP`：事件首次创建时间（UTC），之后不再改变。
   - `LAST-MODIFIED`：内容最近一次修改时间（UTC）。
   - `SEQUENCE`：事件修订号，内容改变时 +1。
3. 仅在事件真实内容变化时更新 `LAST-MODIFIED` / `SEQUENCE`，否则保持不动。
4. 支持通过本地 JSON 状态文件 (`ical_state.json`) 跨多次运行记忆历史。

## 工作流程概述
1. 读取课程解析结果 `events`。
2. 为每个事件生成 UID：`课程名-日期-节次@gdut-course-exporter`（会做清洗/小写）。
3. 计算内容哈希（字段：课程名、日期、节次、教师、地点、起止时间）。
4. 读取 `ical_state.json`（若存在），匹配 UID：
   - 不存在：首次创建 → `sequence=0`，`dtstamp=now`，`last-modified=now`。
   - 存在且 `content_hash` 未变：沿用旧的 `dtstamp`、`last-modified`、`sequence`。
   - 存在且 `content_hash` 变了：`sequence+1`，保留旧 `dtstamp`，`last-modified=now`。
5. 写出 `.ics` 文件。
6. 更新保存新的 `ical_state.json`。

## 状态文件结构示例 (`ical_state.json`)
```json
{
  "shuxue-2025-09-10-0102@gdut-course-exporter": {
    "dtstamp": "2025-09-01T12:30:05+00:00",
    "last_modified": "2025-09-05T09:10:02+00:00",
    "sequence": 1,
    "content_hash": "91bd0e12...",
    "status": "updated"
  },
  "yingyu-2025-09-11-0304@gdut-course-exporter": {
    "dtstamp": "2025-09-01T12:35:11+00:00",
    "last_modified": "2025-09-01T12:35:11+00:00",
    "sequence": 0,
    "content_hash": "a8f3c9d7...",
    "status": "created"
  }
}
```
字段含义：
- `dtstamp`：首次生成时的 UTC 时间（保持原样）。
- `last_modified`：最近一次内容变化时间。
- `sequence`：修订次数。
- `content_hash`：用于判断内容是否变化。
- `status`：本次生成的状态标签（调试用，可删）。

## 何为“内容变化”？
以下任一字段改变即视为内容变化：
- 课程名 `name`
- 上课日期 `date`
- 节次编码 `periods`
- 教师 `teacher`
- 地点 `location`
- 由节次推导的起止时间（映射变化也会触发）

## 日历级元数据
已添加：
- `CALSCALE:GREGORIAN`
- `X-WR-CALNAME: GDUT 课程表`（可传参覆盖）
- `X-WR-TIMEZONE: <配置时区>`

## 如何禁用状态持久化？
调用 `create_calendar_file` 时传入：
```python
create_calendar_file(events, class_time_map, tz, filename, state_path=None)
```
或设置 `state_path=False`。此时：
- 不读取也不写入 `ical_state.json`
- 每次运行所有事件的时间戳为当前时间，订阅端可能视为全部更新。

## 典型订阅更新过程
1. 你部署（覆盖）同一 URL 的最新 `*.ics`。
2. 客户端周期性拉取（Apple 大约 15 分钟到数小时不等；Google 可能 8~24 小时）。
3. 客户端比对：根据 UID 定位事件 → 根据 `SEQUENCE` / `LAST-MODIFIED` 判断是否刷新。
4. 未变化的事件跳过，变化的事件覆盖更新。

## 删除 / 取消 (STATUS:CANCELLED)
当某条课程在新一轮生成中消失，而它曾存在于上一轮 `ical_state.json`：
1. 生成一个带 `STATUS:CANCELLED` 的 VEVENT；
2. `SEQUENCE` 在原基础上 +1；
3. 保留原 `DTSTAMP`，更新 `LAST-MODIFIED`；
4. 仍携带原 `DTSTART` / `DTEND` 以便订阅端匹配；
5. 这样大多数日历会从视图中删除或标记取消该课程。

注意：
- 如果 state 中缺少原始起止时间（极端损坏），该条取消会被跳过。
- 若未来同 UID 又重新出现，将继续递增 `SEQUENCE`，客户端会再次显示（视实现）。

不想产生取消事件：删除或清空 `ical_state.json` 后重新生成（客户端会把所有当作新事件，而不会看到取消指令）。

## 何时需要删除 `ical_state.json`？
- 切换到全新学期且所有课程集合完全不同。
- 状态文件损坏（JSON 无法解析）。
- 想强制订阅端“全部当作新内容”重新吸收。

## 常见问题 (FAQ)
Q: 为什么我的日历客户端没有立刻显示更新？
A: 大多数客户端不会实时推送，需要等它的刷新周期；可以手动“重新获取/刷新”测试。

Q: 如果我修改了节次到时间的映射，会检测到变化吗？
A: 会。因为起止时间的 ISO 字符串在 `content_hash` 中。如果只想修改显示但不触发更新，需要保持生成的时间不变。

Q: `SEQUENCE` 和 `LAST-MODIFIED` 哪个更重要？
A: 二者都重要；少数实现优先看 `SEQUENCE`，大部分也接受 `LAST-MODIFIED`。我们同时维护以最大兼容性。

Q: 可以把 `status` 字段去掉吗？
A: 可以，它只存在于本地 state 文件，订阅端不会看到。调试稳定后可清理。

## 接口签名（当前）
```python
def create_calendar_file(events, class_time_map, timezone, filename, *, state_path="ical_state.json", calendar_name="GDUT 课程表"):
    ...
```
参数说明：
- `events`: 解析后的课程事件列表（来自 `parser.parse_schedule_data`）。
- `class_time_map`: 节次到 (开始, 结束) 时间的元组映射。
- `timezone`: 形如 `Asia/Shanghai`。
- `filename`: 输出 ICS 文件名。
- `state_path`: 状态文件路径；None/False 禁用增量。
- `calendar_name`: 订阅端显示的日历名称。

## 后续可扩展点
- 支持课程合并（多节连续）时的更智能 UID。
- 记录删除的事件（目前删除不会写入 ICS；可以通过保留旧 UID 并写 STATUS:CANCELLED 方式通知订阅端）。
- 增加可选日志级别控制。

---
如需进一步定制（例如 STATUS:CANCELLED / 颜色分类 / 分组），可以在此基础上继续扩展。
