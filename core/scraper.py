# core/scraper.py
import requests
import ddddocr
from PIL import Image
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

    def login(self, account, password):
        print("正在尝试自动识别验证码登录...")
        try:
            captcha_url = f"{self.base_url}/yzm?d=1"
            captcha_response = self.session.get(captcha_url)
            captcha_response.raise_for_status()
            
            verify_code = self.ocr.classification(captcha_response.content)
            print(f"OCR 识别结果: {verify_code}")

            if len(verify_code) != 4:
                print("验证码识别失败，结果非4位，请检查或重试。")
                return False

            # 根据登录验证逻辑准备16字节的AES密钥 ↓↓↓ ---
            encryption_key = (verify_code * 4)[:16]

            password_encrypted = self.provider_config["encrypt_password_func"](password, encryption_key)
            
            login_data = {'account': account, 'pwd': password_encrypted, 'verifycode': verify_code}
            login_url = f"{self.base_url}/new/login"
            login_response = self.session.post(login_url, data=login_data)
            login_response.raise_for_status()
            
            response_json = login_response.json()
            if response_json.get("code", -1) < 0:
                print(f"登录失败: {response_json.get('message')}")
                return False

            print("登录成功！")
            return True
        except Exception as e:
            print(f"登录过程中出错: {e}")
            return False

    def get_schedule_data(self, academic_year, week):
        print(f"正在获取第 {week} 周的课表...")
        try:
            main_page_url = f"{self.base_url}/xsgrkbcx!xskbList.action?xnxqdm={academic_year}&zc={week}"
            self.session.get(main_page_url).raise_for_status()
            
            data_url = f"{self.base_url}/xsgrkbcx!getKbRq.action?xnxqdm={academic_year}&zc={week}"
            headers = self.headers.copy()
            headers['Referer'] = main_page_url
            response = self.session.get(data_url, headers=headers)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"错误：获取第 {week} 周数据时网络请求失败: {e}")
            return None