# core/scraper.py
import requests
import ddddocr
from PIL import Image
import time

if not hasattr(Image, 'ANTIALIAS'):
    setattr(Image, 'ANTIALIAS', Image.LANCZOS)

class Scraper:
    def __init__(self, provider_config):
        self.base_url = provider_config["base_url"]
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # The unsupported 'show_ad' argument has been removed below
        self.ocr = ddddocr.DdddOcr()
        self.provider_config = provider_config

    def _get_captcha_and_ocr(self, max_ocr_retries=3):
        """
        获取验证码图片并进行OCR识别。
        返回 (verify_code, success) 元组。
        """
        for ocr_attempt in range(1, max_ocr_retries + 1):
            try:
                print(f"    获取验证码图片 (OCR尝试 {ocr_attempt}/{max_ocr_retries})...")
                captcha_url = f"{self.base_url}/yzm?d=1"
                captcha_response = self.session.get(captcha_url, timeout=10)
                captcha_response.raise_for_status()
                
                print("    正在进行OCR识别...")
                verify_code = self.ocr.classification(captcha_response.content)
                print(f"    OCR 识别结果: {verify_code}")

                if len(verify_code) == 4:
                    return verify_code, True # 成功识别4位验证码
                else:
                    print(f"    验证码识别失败，结果为 '{verify_code}' ({len(verify_code)} 位)，需要4位。")
                    if ocr_attempt < max_ocr_retries:
                        print("    等待1秒后重试OCR...")
                        time.sleep(1)
            except requests.exceptions.RequestException as e:
                print(f"    获取验证码时网络请求失败: {e}")
                if ocr_attempt < max_ocr_retries:
                    print("    等待2秒后重试获取验证码...")
                    time.sleep(2)
            except Exception as e:
                print(f"    验证码处理过程中发生未预期错误: {e}")
                if ocr_attempt < max_ocr_retries:
                    print("    等待2秒后重试获取验证码...")
                    time.sleep(2)
        return None, False # OCR重试次数用完仍未成功

    def login(self, account, password):
        print("正在尝试自动识别验证码登录...")
        max_login_retries = 3
        for login_attempt in range(1, max_login_retries + 1):
            print(f"  登录尝试 {login_attempt}/{max_login_retries}...")
            
            # 1. 获取验证码和OCR识别
            verify_code, ocr_success = self._get_captcha_and_ocr()
            if not ocr_success:
                print(f"  第 {login_attempt} 次登录尝试：验证码OCR识别连续失败。")
                if login_attempt < max_login_retries:
                    print("  等待2秒后进行下次登录尝试...")
                    time.sleep(2)
                continue # 重试整个登录过程（包括重新获取验证码）

            # 2. 准备登录数据
            try:
                # 根据登录验证逻辑准备16字节的AES密钥 ↓↓↓ ---
                encryption_key = (verify_code * 4)[:16]
                password_encrypted = self.provider_config["encrypt_password_func"](password, encryption_key)
                login_data = {'account': account, 'pwd': password_encrypted, 'verifycode': verify_code}
            except Exception as e:
                print(f"  加密密码时出错: {e}")
                return False # 加密错误通常是配置或代码问题，重试无意义

            # 3. 发送登录请求
            try:
                print("  正在提交登录请求...")
                login_url = f"{self.base_url}/new/login"
                login_response = self.session.post(login_url, data=login_data, timeout=10)
                login_response.raise_for_status()
                
                try:
                    response_json = login_response.json()
                except ValueError as e: # json.JSONDecodeError inherits from ValueError
                    print(f"  登录响应非JSON格式，可能存在系统问题。响应内容前100字符: {login_response.text[:100]}")
                    if login_attempt < max_login_retries:
                        print("  等待3秒后进行下次登录尝试...")
                        time.sleep(3)
                    continue # 重试整个登录过程

                code = response_json.get("code", -1)
                message = response_json.get('message', '未知错误')
                if code >= 0:
                    print("登录成功！")
                    return True
                else:
                    # 登录失败
                    # 尝试提供更具体的错误信息
                    if "验证码" in message or code == -3:
                        print(f"  登录失败: 验证码错误。")
                        # 验证码错误，应在下次尝试时重新获取
                    elif "密码" in message or "用户" in message or code in [-1, -2]:
                         print(f"  登录失败: 账号或密码错误。请检查配置。")
                         # 账号密码错误，重试无意义，可以直接返回失败
                         return False
                    else:
                        print(f"  登录失败: {message} (错误代码: {code})")
                    
                    if login_attempt < max_login_retries:
                        wait_time = 2 if "验证码" in message or code == -3 else 3
                        print(f"  等待{wait_time}秒后进行下次登录尝试...")
                        time.sleep(wait_time)
                    # 循环结束，进行下次登录尝试（包括重新获取验证码）
                        
            except requests.exceptions.Timeout:
                print("  登录请求超时。")
            except requests.exceptions.ConnectionError:
                print("  登录请求连接失败。")
            except requests.exceptions.RequestException as e:
                print(f"  登录时发生网络错误: {e}")
            except Exception as e:
                print(f"  登录过程中发生未预期错误: {e}")
            
            if login_attempt < max_login_retries:
                print("  等待3秒后进行下次登录尝试...")
                time.sleep(3)
        
        print(f"登录连续失败 {max_login_retries} 次，登录终止。")
        return False

    def get_schedule_data(self, academic_year, week):
        print(f"正在获取第 {week} 周的课表...")
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                main_page_url = f"{self.base_url}/xsgrkbcx!xskbList.action?xnxqdm={academic_year}&zc={week}"
                print(f"  访问课表主页 (尝试 {attempt}/{max_retries})...")
                main_page_response = self.session.get(main_page_url, timeout=10)
                main_page_response.raise_for_status()
                
                data_url = f"{self.base_url}/xsgrkbcx!getKbRq.action?xnxqdm={academic_year}&zc={week}"
                headers = self.headers.copy()
                headers['Referer'] = main_page_url
                print(f"  获取课表数据 (尝试 {attempt}/{max_retries})...")
                response = self.session.get(data_url, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"  获取课表数据失败，HTTP状态码: {response.status_code}")
                    if attempt < max_retries:
                        print("  等待2秒后重试...")
                        time.sleep(2)
                    continue # 重试

                response.raise_for_status() # 检查其他HTTP错误
                print(f"  第 {week} 周课表数据获取成功。")
                return response.text
            except requests.exceptions.Timeout:
                print(f"  获取第 {week} 周数据时请求超时。")
            except requests.exceptions.ConnectionError:
                print(f"  获取第 {week} 周数据时连接失败。")
            except requests.exceptions.RequestException as e:
                print(f"  获取第 {week} 周数据时发生网络错误: {e}")
            except Exception as e:
                print(f"  获取第 {week} 周数据时发生未预期错误: {e}")
            
            if attempt < max_retries:
                print("  等待3秒后重试...")
                time.sleep(3)
        
        print(f"获取第 {week} 周课表数据连续失败 {max_retries} 次。")
        return None