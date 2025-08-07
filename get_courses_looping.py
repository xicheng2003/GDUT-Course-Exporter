import requests
from bs4 import BeautifulSoup
import os 
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    setattr(Image, 'ANTIALIAS', Image.LANCZOS)
from Crypto.Cipher import AES
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import json
import config # 导入配置文件
import time   # 导入time模块用于添加延迟
import ddddocr # <-- 新增：导入ddddocr库

# --- 1. 配置区 ---
ACADEMIC_YEAR_SEMESTER = "202501"  # 目标学年学期代码
TOTAL_SEMESTER_WEEKS = 20         # !! 学期总周数，请根据校历修改 !!

OUTPUT_FILENAME = "my_courses_semester.ics" # 输出的日历文件名
TIMEZONE = "Asia/Shanghai" # 时区

# 广东工业大学作息时间
CLASS_TIME_MAP = {
    "01": ("08:30", "09:15"), "02": ("09:20", "10:05"), "03": ("10:25", "11:10"),
    "04": ("11:15", "12:00"), "05": ("13:50", "14:35"), "06": ("14:40", "15:25"),
    "07": ("15:30", "16:15"), "08": ("16:30", "17:15"), "09": ("17:20", "18:05"),
    "10": ("18:30", "20:15"), "11": ("20:20", "21:05"),
}

BASE_URL = "https://jxfw.gdut.edu.cn"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
}

# --- 2. 辅助函数 ---

def encrypt_password(password, key):
    """使用AES/ECB/PKCS7Padding加密密码，返回Hex字符串。"""
    key_bytes = key.encode('utf-8')
    password_bytes = password.encode('utf-8')
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    block_size = AES.block_size
    padding_len = block_size - (len(password_bytes) % block_size)
    padded_password = password_bytes + (chr(padding_len) * padding_len).encode('utf-8')
    encrypted_bytes = cipher.encrypt(padded_password)
    return encrypted_bytes.hex()

def fetch_and_parse_weekly_data(session, week):
    """获取并解析指定周的课表数据，返回事件字典列表。"""
    print(f"正在获取第 {week} 周的课表...")
    try:
        main_page_url = f"{BASE_URL}/xsgrkbcx!xskbList.action?xnxqdm={ACADEMIC_YEAR_SEMESTER}&zc={week}"
        session.get(main_page_url).raise_for_status()
        
        data_url = f"{BASE_URL}/xsgrkbcx!getKbRq.action?xnxqdm={ACADEMIC_YEAR_SEMESTER}&zc={week}"
        headers = HEADERS.copy()
        headers['Referer'] = main_page_url
        response = session.get(data_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        json_string = soup.find('p').get_text(strip=True)
        # 如果当周无课，返回的可能是空字符串或不合法的JSON
        if not json_string or json_string.isspace():
            print(f"第 {week} 周没有课程安排。")
            return []
            
        raw_data = json.loads(json_string)
        
        courses_list, date_mapping_list = raw_data[0], raw_data[1]
        date_map = {item['xqmc']: item['rq'] for item in date_mapping_list}
        
        events = []
        for course in courses_list:
            day_of_week = course.get('xq')
            course_date_str = date_map.get(day_of_week)
            if not course_date_str: continue

            # 创建一个唯一的标识符来处理同一节课在同一周有多个安排（例如地点不同）
            # 我们将所有信息组合成一个元组
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
    except json.JSONDecodeError:
        print(f"警告：解析第 {week} 周数据时出错，可能当周无课。")
        return []
    except requests.exceptions.RequestException as e:
        print(f"错误：获取第 {week} 周数据时网络请求失败: {e}")
        return []

def create_calendar_file(events, filename):
    """根据事件列表，创建并保存.ics文件。"""
    # (此函数无需修改，和之前一样)
    cal = Calendar()
    cal.add('prodid', '-//GDUT Course Calendar//lxc52.com//')
    cal.add('version', '2.0')
    tz = pytz.timezone(TIMEZONE)

    if not events:
        print("没有课程事件可以生成。")
        return

    for event_data in events:
        start_period = event_data["periods"][:2]
        end_period = event_data["periods"][-2:]
        start_time_str = CLASS_TIME_MAP.get(start_period, ("00:00", ""))[0]
        end_time_str = CLASS_TIME_MAP.get(end_period, ("", "00:00"))[1]

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

# --- 3. 主执行逻辑 ---
def main():
    """主执行函数"""
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # <-- 新增：初始化一次ddddocr识别器
    ocr = ddddocr.DdddOcr() 
    
    # --- 登录 (修改为ddddocr自动识别验证码版本) ---
    try:
        print("正在尝试自动识别验证码登录...")
        captcha_url = f"{BASE_URL}/yzm?d=1"
        captcha_response = session.get(captcha_url)
        captcha_response.raise_for_status()
        
        # <-- 修改：使用ddddocr识别验证码，替换手动输入
        verify_code = ocr.classification(captcha_response.content)
        print(f"OCR 识别结果: {verify_code}")

        # <-- 新增：简单校验识别结果的有效性
        if len(verify_code) != 4:
            print("验证码识别失败，结果非4位，请检查或重试。")
            return
        
        encryption_key = (verify_code * 4)[:16]

        # 从环境变量获取账号密码
        account = os.environ.get('GDUT_ACCOUNT')
        password = os.environ.get('GDUT_PASSWORD')

        if not account or not password:
            print("错误：环境变量 GDUT_ACCOUNT 或 GDUT_PASSWORD 未设置。")
            return # 直接退出

        password_encrypted = encrypt_password(password, encryption_key)
        login_data = {'account': account, 'pwd': password_encrypted, 'verifycode': verify_code}

        login_url = f"{BASE_URL}/new/login"
        login_response = session.post(login_url, data=login_data)
        login_response.raise_for_status()
        
        response_json = login_response.json()
        if response_json.get("code", -1) < 0:
            print(f"登录失败: {response_json.get('message')}")
            print("失败原因可能是验证码自动识别错误，或账号密码不正确。")
            return
        print("登录成功！")
    except Exception as e:
        print(f"登录过程中出错: {e}")
        return

    # --- 轮询获取整个学期的课表 ---
    all_semester_events = {} # 使用字典来自动去重
    for week in range(1, TOTAL_SEMESTER_WEEKS + 1):
        weekly_events = fetch_and_parse_weekly_data(session, week)
        for event in weekly_events:
            # 使用unique_id作为键，确保每个独特的课程安排只被添加一次
            all_semester_events[event['id']] = event
        
        # 友好提示，并稍微延迟，避免请求过于频繁
        time.sleep(0.5) 

    # --- 生成日历 ---
    final_event_list = list(all_semester_events.values())
    if final_event_list:
        create_calendar_file(final_event_list, OUTPUT_FILENAME)
    else:
        print("未能获取到任何课程信息，无法生成日历。")

if __name__ == '__main__':
    try:
        main()
    finally:
        input("程序已结束，按任意键退出...")