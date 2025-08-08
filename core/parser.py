# core/parser.py
import json
from bs4 import BeautifulSoup

def parse_schedule_data(response_text):
    """
    健壮地解析课表数据。
    优先尝试直接解析JSON，如果失败，则尝试从HTML的<p>标签中提取JSON。
    """
    if not response_text or response_text.isspace():
        return []

    try:
        # 优先尝试直接作为JSON解析 (适用于服务器环境)
        raw_data = json.loads(response_text)
    except json.JSONDecodeError:
        # 如果直接解析失败，则尝试作为HTML解析 (适用于本地环境)
        print("直接解析JSON失败，尝试从HTML <p>标签中提取...")
        try:
            soup = BeautifulSoup(response_text, 'lxml')
            p_tag = soup.find('p')
            if p_tag:
                json_string = p_tag.get_text(strip=True)
                raw_data = json.loads(json_string)
            else:
                print("在HTML中也未找到<p>标签。")
                return []
        except Exception as e:
            print(f"从HTML中提取并解析JSON时出错: {e}")
            return []

    # --- 后续的解析逻辑保持不变 ---
    if not raw_data or not raw_data[0]:
        return []

    courses_list, date_mapping_list = raw_data[0], raw_data[1]
    date_map = {item['xqmc']: item['rq'] for item in date_mapping_list}
    
    events = []
    for course in courses_list:
        day_of_week = course.get('xq')
        course_date_str = date_map.get(day_of_week)
        if not course_date_str: continue

        unique_id = (
            course_date_str,
            course.get('jcdm'),
            course.get('kcmc'),
            course.get('teaxms'),
            course.get('jxcdmc')
        )
        
        event_details = {
            "id": unique_id,
            "name": course.get('kcmc'), "teacher": course.get('teaxms'),
            "location": course.get('jxcdmc'), "periods": course.get('jcdm'),
            "date": course_date_str
        }
        events.append(event_details)
    return events