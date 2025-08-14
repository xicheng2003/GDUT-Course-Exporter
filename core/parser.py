# core/parser.py
import json
import re
from bs4 import BeautifulSoup

def _log_snippet(text, msg_prefix=""):
    """安全地记录文本片段用于调试"""
    if not text:
        print(f"{msg_prefix}响应内容为空。")
        return
    # 移除或替换可能影响日志显示的控制字符
    snippet = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '?', text[:200])
    print(f"{msg_prefix}响应内容片段: {snippet}")

def parse_schedule_data(response_text):
    """
    健壮地解析课表数据。
    优先尝试直接解析JSON，如果失败，则尝试从HTML的<p>标签中提取JSON。
    """
    if not response_text or response_text.isspace():
        print("  警告：收到空的或仅包含空白字符的课表响应。")
        return []

    # 1. 尝试直接作为JSON解析 (适用于服务器环境)
    try:
        print("  尝试直接解析JSON数据...")
        raw_data = json.loads(response_text)
        print("  JSON数据解析成功。")
    except json.JSONDecodeError as e1:
        _log_snippet(response_text, "  直接解析JSON失败: ")
        # 2. 如果直接解析失败，则尝试作为HTML解析 (适用于本地环境)
        print("  尝试从HTML <p>标签中提取JSON...")
        try:
            soup = BeautifulSoup(response_text, 'lxml')
            p_tag = soup.find('p')
            if p_tag:
                json_string = p_tag.get_text(strip=True)
                # 再次尝试解析提取出的字符串
                raw_data = json.loads(json_string)
                print("  从HTML中提取JSON并解析成功。")
            else:
                print("  在HTML响应中未找到<p>标签，无法提取JSON。")
                _log_snippet(response_text)
                return []
        except json.JSONDecodeError as e2:
            print(f"  从HTML <p>标签提取的文本也无法解析为JSON: {e2}")
            _log_snippet(response_text)
            return []
        except Exception as e:
            print(f"  从HTML中提取并解析JSON时发生未预期错误: {e}")
            _log_snippet(response_text)
            return []
    except Exception as e:
        print(f"  直接解析JSON时发生未预期错误: {e}")
        _log_snippet(response_text)
        return []

    # --- 后续的解析逻辑 ---
    # 检查数据结构是否符合预期
    if not isinstance(raw_data, list) or len(raw_data) < 2:
        print("  警告：解析出的JSON数据结构不符合预期 (应为至少包含两个元素的列表)。")
        _log_snippet(json.dumps(raw_data) if isinstance(raw_data, (dict, list)) else str(raw_data))
        return []
        
    courses_list, date_mapping_list = raw_data[0], raw_data[1]
    
    if not courses_list:
        print("  警告：解析出的课程列表为空。")
        return []
    if not date_mapping_list:
        print("  警告：解析出的日期映射列表为空。")
        _log_snippet(json.dumps(raw_data))
        # 即使日期映射为空，也返回课程列表，让后续处理决定
        
    try:
        date_map = {item['xqmc']: item['rq'] for item in date_mapping_list}
    except (KeyError, TypeError) as e:
        print(f"  警告：解析日期映射列表时出错，可能存在数据结构变化: {e}")
        _log_snippet(json.dumps(date_mapping_list[:5]) if isinstance(date_mapping_list, list) else str(date_mapping_list))
        date_map = {} # 如果日期映射失败，后续课程处理会跳过

    events = []
    for course in courses_list:
        # 使用 get 避免 KeyError，但需要检查关键字段是否存在
        day_of_week = course.get('xq')
        course_date_str = date_map.get(day_of_week) if day_of_week else None
        
        # 跳过没有有效日期的课程（可能是日期映射失败）
        if not course_date_str: 
            # 可以选择打印警告，但日志可能过多
            # print(f"  警告：无法为课程 '{course.get('kcmc', 'Unknown')}' 找到有效日期 (星期: {day_of_week})。")
            continue 

        # 构建唯一ID和事件详情
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
    
    print(f"  成功解析出 {len(events)} 个课程事件。")
    return events