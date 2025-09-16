import os
import json
from datetime import datetime
from core.ical_generator import create_calendar_file, STATE_DEFAULT_FILENAME

# 简易 class_time_map (示例)
example_class_time_map = {
    '01': ('08:00', '08:45'),
    '02': ('08:50', '09:35'),
    '03': ('09:50', '10:35'),
    '04': ('10:40', '11:25'),
}

# 初始事件集合
events_round1 = [
    {"name": "数学", "teacher": "张三", "location": "教学楼A101", "periods": "0102", "date": "2025-09-10"},
    {"name": "英语", "teacher": "李四", "location": "教学楼B202", "periods": "0304", "date": "2025-09-10"},
]

# 第二轮：修改数学地点，删除英语，新增 物理
events_round2 = [
    {"name": "数学", "teacher": "张三", "location": "教学楼A102", "periods": "0102", "date": "2025-09-10"},  # update
    {"name": "物理", "teacher": "王五", "location": "实验楼C303", "periods": "0304", "date": "2025-09-11"},  # new
]


def run_cycle(label, events):
    print(f"\n===== 生成轮次: {label} =====")
    create_calendar_file(events, example_class_time_map, 'Asia/Shanghai', f"my_courses_{label}.ics")


def main():
    # 清理旧状态
    if os.path.exists(STATE_DEFAULT_FILENAME):
        os.remove(STATE_DEFAULT_FILENAME)
        print("已删除旧 state 文件。")
    # 第一轮
    run_cycle('round1', events_round1)
    # 第二轮
    run_cycle('round2', events_round2)
    # 显示最终 state
    if os.path.exists(STATE_DEFAULT_FILENAME):
        print("\n最终 state 文件内容片段:")
        with open(STATE_DEFAULT_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for k, v in list(data.items())[:5]:
                print(k, v)

if __name__ == '__main__':
    main()
