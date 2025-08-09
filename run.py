# run.py
import os
import sys
import yaml
import time
import os.path
from dotenv import load_dotenv
from importlib import import_module

# 导入核心模块
from core.scraper import Scraper
from core.parser import parse_schedule_data
from core.ical_generator import create_calendar_file
from core.utils import get_current_academic_semester

def main():
    # 加载.env文件中的环境变量（如果存在）
    load_dotenv()

    # 加载配置文件
    try:
        with open("config.yml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("错误：未找到 config.yml 配置文件。")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"错误：config.yml 配置文件格式有误: {e}")
        sys.exit(1)

    # --- 1. 加载学校适配器 ---
    provider_name = config["provider"]
    try:
        provider_module = import_module(f"providers.{provider_name}")
        provider_config = getattr(provider_module, f"{provider_name.upper()}_PROVIDER")
        print(f"已加载适配器: {provider_config['name']}")
    except (ImportError, AttributeError) as e:
        print(f"错误：无法加载名为 '{provider_name}' 的适配器。请检查 providers 目录和配置。详细信息: {e}")
        sys.exit(1)

    # --- 2. 获取用户凭据 (环境变量优先) ---
    account = os.environ.get('ACCOUNT') or config.get('credentials', {}).get('account')
    password = os.environ.get('PASSWORD') or config.get('credentials', {}).get('password')

    if not account or not password or "YOUR_ACCOUNT_HERE" in account:
        print("错误：未找到有效的账号或密码配置。")
        print("请在环境变量中设置 ACCOUNT 和 PASSWORD，或在 config.yml 中填写 credentials。")
        # 提示用户检查配置文件路径
        config_path = os.path.abspath("config.yml")
        print(f"请确认配置文件位于: {config_path}")
        sys.exit(1)

    # --- 3. 执行核心流程 ---
    scraper = Scraper(provider_config)

    if not scraper.login(account, password):
        print("[错误] 登录失败，流程终止。")
        print("请检查以下几点：")
        print("1. 账号和密码是否正确。")
        print("2. 验证码是否能被正确识别（如果一直失败，可能是教务系统变更）。")
        print("3. 网络连接是否正常。")
        sys.exit(1)

    # --- 判断学期设置为手动或者自动 ---
    academic_year_semester = config.get("academic_year_semester")
    # 如果配置为空或设置为'auto'，则根据日期自动计算当前学期
    if not academic_year_semester or str(academic_year_semester).lower() == 'auto':
        academic_year_semester = get_current_academic_semester()
        print(f"检测到学期设置为自动，已计算当前学期为: {academic_year_semester}")

    all_semester_events = {}
    failed_weeks = []
    total_weeks = config["total_semester_weeks"]
    print(f"--- 开始获取 {total_weeks} 周的课表数据 ---")
    for week in range(1, total_weeks + 1):
        response_text = scraper.get_schedule_data(academic_year_semester, week)
        if response_text is not None: # 空字符串也是有效响应
            print(f"  解析第 {week} 周数据...")
            weekly_events = parse_schedule_data(response_text)
            if not weekly_events:
                 print(f"  警告：第 {week} 周数据解析后未生成任何事件。")
            for event in weekly_events:
                # 使用课程的唯一ID去重
                all_semester_events[event['id']] = event
        else:
            print(f"  第 {week} 周数据获取失败。")
            failed_weeks.append(week)
        # 避免请求过于频繁
        if week < total_weeks: # 最后一周后不需要sleep
            time.sleep(0.5)

    # --- 4. 生成日历文件 ---
    final_event_list = list(all_semester_events.values())
    print(f"--- 数据获取与解析完成 ---")
    print(f"成功获取并解析了 {len(final_event_list)} 个不重复的课程事件。")
    if failed_weeks:
        print(f"以下周次数据获取失败: {failed_weeks}")
        if len(failed_weeks) > total_weeks / 2:
            print("警告：超过一半的周次数据获取失败，生成的日历文件可能不完整。")

    if final_event_list:
        output_filename = config["output_filename"]
        try:
            create_calendar_file(
                final_event_list,
                provider_config["class_time_map"],
                config["timezone"],
                output_filename
            )
            # 提供文件的绝对路径，方便用户查找
            file_path = os.path.abspath(output_filename)
            print(f"日历文件已保存至: {file_path}")
        except Exception as e:
            print(f"[错误] 生成日历文件时发生错误: {e}")
            sys.exit(1)
    else:
        print("[错误] 未能获取到任何有效的课程信息，无法生成日历文件。")
        print("请回顾上方日志，检查是否有持续的网络错误、数据解析错误或所有周次均为空。")
        sys.exit(1)

if __name__ == '__main__':
    main()