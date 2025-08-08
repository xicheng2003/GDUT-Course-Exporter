# core/ical_generator.py
from icalendar import Calendar, Event
from datetime import datetime
import pytz

def create_calendar_file(events, class_time_map, timezone, filename):
    cal = Calendar()
    cal.add('prodid', '-//Universal Course Calendar//github.com//')
    cal.add('version', '2.0')
    tz = pytz.timezone(timezone)

    if not events:
        print("没有课程事件可以生成。")
        return

    for event_data in events:
        start_period = event_data["periods"][:2]
        end_period = event_data["periods"][-2:]
        start_time_str = class_time_map.get(start_period, ("00:00", ""))[0]
        end_time_str = class_time_map.get(end_period, ("", "00:00"))[1]

        start_dt = datetime.strptime(f"{event_data['date']} {start_time_str}", '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(f"{event_data['date']} {end_time_str}", '%Y-%m-%d %H:%M')

        event = Event()
        event.add('summary', event_data["name"])
        event.add('dtstart', tz.localize(start_dt))
        event.add('dtend', tz.localize(end_dt))
        full_location = f'{event_data["location"]} {event_data["teacher"]}'
        event.add('location', full_location)
        event.add('description', f"教师: {event_data['teacher']}\n节次: {event_data['periods']}")
        cal.add_component(event)

    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
    print(f"\n--- 日历文件已成功生成 ---")
    print(f"文件名: {filename}")