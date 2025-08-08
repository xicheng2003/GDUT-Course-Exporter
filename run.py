# run.py
import os
import sys
import yaml
import time
from dotenv import load_dotenv
from importlib import import_module

# 导入核心模块
from core.scraper import Scraper
from core.parser import parse_schedule_data
from core.ical_generator import create_calendar_file

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

    # --- 1. 加载学校适配器 ---
    provider_name = config["provider"]
    try:
        provider_module = import_module(f"providers.{provider_name}")
        provider_config = getattr(provider_module, f"{provider_name.upper()}_PROVIDER")
        print(f"已加载适配器: {provider_config['name']}")
    except (ImportError, AttributeError):
        print(f"错误：无法加载名为 '{provider_name}' 的适配器。请检查 providers 目录和配置。")
        sys.exit(1)

    # --- 2. 获取用户凭据 (环境变量优先) ---
    account = os.environ.get('ACCOUNT') or config.get('credentials', {}).get('account')
    password = os.environ.get('PASSWORD') or config.get('credentials', {}).get('password')

    if not account or not password or "YOUR_ACCOUNT_HERE" in account:
        print("错误：未找到有效的账号或密码配置。")
        print("请在环境变量中设置 ACCOUNT 和 PASSWORD，或在 config.yml 中填写 credentials。")
        sys.exit(1)

    # --- 3. 执行核心流程 ---
    scraper = Scraper(provider_config)

    if not scraper.login(account, password):
        print("流程终止。")
        sys.exit(1)

    all_semester_events = {}
    for week in range(1, config["total_semester_weeks"] + 1):
        response_text = scraper.get_schedule_data(config["academic_year_semester"], week)
        if response_text:
            weekly_events = parse_schedule_data(response_text)
            for event in weekly_events:
                all_semester_events[event['id']] = event
        time.sleep(0.5)

    # --- 4. 生成日历文件 ---
    final_event_list = list(all_semester_events.values())
    if final_event_list:
        create_calendar_file(
            final_event_list,
            provider_config["class_time_map"],
            config["timezone"],
            config["output_filename"]
        )
    else:
        print("未能获取到任何课程信息，无法生成日历。")

if __name__ == '__main__':
    main()