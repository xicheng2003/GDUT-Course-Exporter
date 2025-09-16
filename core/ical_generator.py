# core/ical_generator.py
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import json
import hashlib
import os


STATE_DEFAULT_FILENAME = "ical_state.json"
DOMAIN_SUFFIX = "gdut-course-exporter"


def _safe_load_state(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            print("[state] 文件内容不是对象，忽略。")
            return {}
    except Exception as e:
        print(f"[state] 读取失败，将忽略旧状态: {e}")
        return {}


def _safe_write_state(path, state):
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[state] 写入失败: {e}")


def _normalize_text(s):
    if s is None:
        return ""
    return str(s).strip().replace("\n", " ")


def _build_uid(event_data):
    # 使用课程名+日期+节次 生成可读且稳定的 UID
    name = _normalize_text(event_data.get("name"))
    date = _normalize_text(event_data.get("date"))
    periods = _normalize_text(event_data.get("periods"))
    base = f"{name}-{date}-{periods}".lower()
    # 去除空白和特殊字符
    safe = ''.join(ch for ch in base if ch.isalnum() or ch in ('-', '_'))
    # 确保不为空
    if not safe:
        safe = hashlib.sha1(base.encode('utf-8')).hexdigest()[:12]
    return f"{safe}@{DOMAIN_SUFFIX}"


def _event_content_hash(fields):
    h = hashlib.sha256()
    for item in fields:
        if isinstance(item, str):
            val = item
        else:
            val = str(item)
        h.update(val.encode('utf-8'))
        h.update(b"|")
    return h.hexdigest()


def create_calendar_file(events, class_time_map, timezone, filename, *, state_path=STATE_DEFAULT_FILENAME, calendar_name="GDUT 课程表"):
    """
    生成日历文件 (ICS)。

    新增特性：
    - 稳定 UID (课程名+日期+节次)
    - DTSTAMP / LAST-MODIFIED / SEQUENCE 管理（基于本地 state 文件）
    - 仅在事件实际内容变化时递增 sequence 和 last-modified
    - 可通过 state_path=None/False 禁用状态持久化
    """
    cal = Calendar()
    cal.add('prodid', '-//Universal Course Calendar//github.com//')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('X-WR-CALNAME', calendar_name)
    cal.add('X-WR-TIMEZONE', timezone)

    tz = pytz.timezone(timezone)
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)

    if not events:
        print("没有课程事件可以生成。")
        return

    # 加载 state
    use_state = bool(state_path)
    state = _safe_load_state(state_path) if use_state else {}
    # 只收集本轮仍存在或新增的事件；删除的将在后面单独检测
    updated_state = {}

    created = 0
    updated = 0
    unchanged = 0
    cancelled = 0

    for event_data in events:
        # 解析时间段
        periods_str = event_data.get("periods", "")
        if len(periods_str) < 2:
            # fallback，跳过异常 period
            print(f"[警告] 节次字段异常: {periods_str} (跳过 UID 逻辑仍尝试生成)")
        start_period = periods_str[:2]
        end_period = periods_str[-2:]
        start_time_str = class_time_map.get(start_period, ("00:00", ""))[0]
        end_time_str = class_time_map.get(end_period, ("", "00:00"))[1]

        # 构造开始结束时间（本地 tz）
        try:
            start_dt_local = tz.localize(datetime.strptime(f"{event_data['date']} {start_time_str}", '%Y-%m-%d %H:%M'))
            end_dt_local = tz.localize(datetime.strptime(f"{event_data['date']} {end_time_str}", '%Y-%m-%d %H:%M'))
        except Exception as e:
            print(f"[错误] 解析时间失败，事件已跳过: {event_data} / {e}")
            continue

        uid = _build_uid(event_data)

        # 构建内容 hash
        content_hash = _event_content_hash([
            event_data.get('name'), event_data.get('date'), periods_str,
            event_data.get('teacher'), event_data.get('location'),
            start_dt_local.isoformat(), end_dt_local.isoformat()
        ])

        prev = state.get(uid) if use_state else None
        if prev is None:
            sequence = 0
            dtstamp = now_utc
            last_modified = now_utc
            status_flag = 'created'
            created += 1
        else:
            # 判断内容是否变化
            if prev.get('content_hash') == content_hash:
                sequence = prev.get('sequence', 0)
                dtstamp = datetime.fromisoformat(prev.get('dtstamp')) if prev.get('dtstamp') else now_utc
                last_modified = datetime.fromisoformat(prev.get('last_modified')) if prev.get('last_modified') else now_utc
                status_flag = 'unchanged'
                unchanged += 1
            else:
                sequence = prev.get('sequence', 0) + 1
                dtstamp = datetime.fromisoformat(prev.get('dtstamp')) if prev.get('dtstamp') else now_utc
                last_modified = now_utc
                status_flag = 'updated'
                updated += 1

        event = Event()
        event.add('uid', uid)
        event.add('summary', event_data.get("name"))
        event.add('dtstart', start_dt_local)
        event.add('dtend', end_dt_local)
        full_location = f"{event_data.get('location','')} {event_data.get('teacher','')}".strip()
        if full_location:
            event.add('location', full_location)
        event.add('description', f"教师: {event_data.get('teacher','')}_节次: {periods_str}")
        event.add('dtstamp', dtstamp)
        event.add('last-modified', last_modified)
        event.add('sequence', sequence)

        cal.add_component(event)

        # 更新状态缓存
        if use_state:
            updated_state[uid] = {
                'dtstamp': dtstamp.isoformat(),
                'last_modified': last_modified.isoformat(),
                'sequence': sequence,
                'content_hash': content_hash,
                'status': status_flag,
                'start': start_dt_local.isoformat(),
                'end': end_dt_local.isoformat(),
                'summary': event_data.get('name') or ''
            }

    # 处理被删除的事件 -> 写入 CANCELLED 事件
    if use_state:
        current_uids = set(updated_state.keys())
        previous_uids = set(state.keys())
        removed = previous_uids - current_uids
        if removed:
            for uid in removed:
                prev = state.get(uid) or {}
                # 需要原始开始结束时间
                try:
                    start_iso = prev.get('start')
                    end_iso = prev.get('end')
                    if not (start_iso and end_iso):
                        print(f"[删除] 跳过无起止时间的 UID: {uid}")
                        continue
                    start_dt = datetime.fromisoformat(start_iso)
                    end_dt = datetime.fromisoformat(end_iso)
                except Exception as e:
                    print(f"[删除] 解析原时间失败 UID {uid}: {e}")
                    continue

                prev_dtstamp = prev.get('dtstamp')
                try:
                    dtstamp_val = datetime.fromisoformat(prev_dtstamp) if prev_dtstamp else now_utc
                except Exception:
                    dtstamp_val = now_utc

                prev_seq = prev.get('sequence', 0)
                seq_new = prev_seq + 1  # 删除视为一次修订

                event = Event()
                event.add('uid', uid)
                event.add('summary', prev.get('summary', '取消的课程'))
                # 对于取消事件仍需提供原 dtstart/dtend 便于匹配覆盖
                try:
                    if start_dt.tzinfo is None:
                        start_dt = tz.localize(start_dt)
                    if end_dt.tzinfo is None:
                        end_dt = tz.localize(end_dt)
                except Exception:
                    pass
                event.add('dtstart', start_dt)
                event.add('dtend', end_dt)
                event.add('status', 'CANCELLED')
                event.add('dtstamp', dtstamp_val)
                event.add('last-modified', now_utc)
                event.add('sequence', seq_new)
                event.add('description', '该课程已被移除 / CANCELLED')
                cal.add_component(event)

                # 写入新状态（保留以防以后再出现可继续递增）
                updated_state[uid] = {
                    'dtstamp': dtstamp_val.isoformat(),
                    'last_modified': now_utc.isoformat(),
                    'sequence': seq_new,
                    'content_hash': prev.get('content_hash', ''),
                    'status': 'cancelled',
                    'start': start_dt.isoformat(),
                    'end': end_dt.isoformat(),
                    'summary': prev.get('summary', '')
                }
                cancelled += 1

    # 写 ICS 文件
    try:
        with open(filename, 'wb') as f:
            f.write(cal.to_ical())
    except Exception as e:
        print(f"[错误] 写入 ICS 文件失败: {e}")
        return

    # 写 state 文件
    if use_state:
        _safe_write_state(state_path, updated_state)

    print(f"\n--- 日历文件已成功生成 ---")
    print(f"文件名: {filename}")
    if use_state:
        print(f"事件统计: 新增 {created} | 更新 {updated} | 未变化 {unchanged} | 取消 {cancelled}")
        print(f"状态文件: {state_path}")
    else:
        print("(未使用状态持久化，所有事件会被订阅端视为可能的更新。)")