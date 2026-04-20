# core/scraper.py
import io
import os
import re
import time
import base64
import random
from urllib.parse import urlencode

import ddddocr
import requests
import urllib3
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PIL import Image, ImageOps

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
        self.session.verify = provider_config.get("ssl_verify", True)
        self._environment_checked = False
        self._last_captcha_bytes = None
        self._last_captcha_note = None
        self._captcha_debug_dir = os.path.abspath("debug_captchas")
        self._ssl_verification_disabled = not self.session.verify
        self._legacy_login_allowed = provider_config.get("legacy_login_allowed", True)
        self._sso_login_url = provider_config.get("sso_login_url")
        self._sso_service_url = provider_config.get("sso_service_url", f"{self.base_url}/new/ssoLogin")
        self._use_sso_login = bool(self._sso_login_url)
        self._sso_redirect_url = None

        if not self.session.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _request(self, method, url, **kwargs):
        """统一处理请求，并在允许时对证书问题做一次不校验证书的回退。"""
        try:
            return self.session.request(method, url, **kwargs)
        except requests.exceptions.SSLError as e:
            if self.provider_config.get("allow_insecure_ssl_fallback", False) and not self._ssl_verification_disabled:
                self._ssl_verification_disabled = True
                self.session.verify = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                print("检测到证书校验失败，已回退为不校验证书继续访问。")
                return self.session.request(method, url, **kwargs)
            raise e

    def _probe_login_environment(self):
        """检测当前学校站点主入口和脚本使用的旧登录链路是否一致。"""
        if self._environment_checked:
            return

        self._environment_checked = True
        try:
            response = self._request("GET", self.base_url, timeout=10, allow_redirects=False)
            location = response.headers.get("Location", "")
            if response.is_redirect and "authserver" in location:
                self._sso_redirect_url = location
                self._use_sso_login = True
                print("检测到学校主入口已切换到统一身份认证（SSO）。")
                print(f"  当前主入口跳转至: {location}")
                if not self._sso_login_url:
                    self._sso_login_url = location.split("?", 1)[0]
                print("  当前将优先使用 SSO 登录，再进入教务系统。")
        except requests.exceptions.RequestException as e:
            print(f"登录环境探测失败，跳过主入口检查: {e}")

    def _extract_script_var(self, html_text, var_name):
        pattern = rf'var\s+{re.escape(var_name)}\s*=\s*"([^"]*)"'
        match = re.search(pattern, html_text)
        return match.group(1) if match else ""

    def _build_sso_login_url(self):
        if not self._sso_login_url:
            return None
        query = urlencode({"service": self._sso_service_url})
        separator = "&" if "?" in self._sso_login_url else "?"
        return f"{self._sso_login_url}{separator}{query}"

    def _sso_random_string(self, length):
        chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
        return "".join(random.choice(chars) for _ in range(length))

    def _encrypt_sso_password(self, password, salt):
        iv = self._sso_random_string(16).encode("utf-8")
        plaintext = (self._sso_random_string(64) + password).encode("utf-8")
        cipher = AES.new(salt.strip().encode("utf-8"), AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(pad(plaintext, AES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")

    def _extract_sso_error(self, html_text):
        soup = BeautifulSoup(html_text, "lxml")
        for selector in ("#showErrorTip", "#formErrorTip .form-error", ".form-error", ".authError"):
            node = soup.select_one(selector)
            if node:
                text = node.get_text(strip=True)
                if text:
                    return text
        return None

    def _check_sso_captcha_requirement(self, account):
        if not self._sso_login_url:
            return False, ""

        auth_base = self._sso_login_url.rsplit("/", 1)[0]
        check_url = f"{auth_base}/checkNeedCaptcha.htl"
        try:
            response = self._request("GET", check_url, params={"username": account}, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            return bool(response_json.get("isNeed")), ""
        except Exception as e:
            return False, f"验证码需求探测失败: {e}"

    def _follow_sso_success_redirect(self, redirect_url):
        try:
            final_response = self._request("GET", redirect_url, timeout=20, allow_redirects=True)
            print(f"  SSO 跳转完成，当前页面: {final_response.url}")
            if "jxfw.gdut.edu.cn" in final_response.url:
                return True
            print("  SSO 登录后未进入教务系统目标页。")
            return False
        except requests.exceptions.RequestException as e:
            print(f"  跟进 SSO 登录跳转失败: {e}")
            return False

    def _login_via_sso(self, account, password):
        sso_login_url = self._build_sso_login_url()
        if not sso_login_url:
            print("未配置 SSO 登录地址，无法执行 SSO 登录。")
            return False

        print("正在尝试通过统一身份认证（SSO）登录...")
        try:
            login_page_response = self._request("GET", sso_login_url, timeout=20)
            login_page_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  获取 SSO 登录页失败: {e}")
            return False

        login_html = login_page_response.text
        soup = BeautifulSoup(login_html, "lxml")
        pwd_form = soup.find("form", id="pwdFromId")
        if not pwd_form:
            print("  未在 SSO 登录页找到用户名密码登录表单。")
            return False

        need_captcha, captcha_probe_error = self._check_sso_captcha_requirement(account)
        if captcha_probe_error:
            print(f"  {captcha_probe_error}")

        captcha_switch = self._extract_script_var(login_html, "captchaSwitch")
        if need_captcha:
            print("  当前账号在 SSO 侧被要求先通过验证码校验。")
            if captcha_switch == "2":
                print("  当前学校启用了滑块验证码，脚本暂不支持自动完成该挑战。")
                return False
            print(f"  检测到验证码开关模式: {captcha_switch or 'unknown'}。")
            print("  当前实现仅处理无需验证码的 SSO 登录场景。")
            return False

        try:
            form_data = {
                tag.get("name"): tag.get("value", "")
                for tag in pwd_form.find_all("input")
                if tag.get("name")
            }
            password_salt = soup.find("input", id="pwdEncryptSalt").get("value", "")
            form_data["username"] = account
            form_data["password"] = self._encrypt_sso_password(password, password_salt)
            form_data.pop("passwordText", None)
            form_data.pop("rememberMe", None)
        except Exception as e:
            print(f"  组装 SSO 登录表单失败: {e}")
            return False

        try:
            login_response = self._request(
                "POST",
                sso_login_url,
                data=form_data,
                timeout=20,
                allow_redirects=False
            )
        except requests.exceptions.RequestException as e:
            print(f"  提交 SSO 登录表单失败: {e}")
            return False

        if login_response.is_redirect:
            redirect_url = login_response.headers.get("Location", "")
            print(f"  SSO 登录已拿到票据跳转: {redirect_url}")
            if not redirect_url:
                print("  SSO 登录返回了重定向，但缺少目标地址。")
                return False
            if self._follow_sso_success_redirect(redirect_url):
                print("SSO 登录成功！")
                return True
            return False

        error_message = self._extract_sso_error(login_response.text)
        if error_message:
            print(f"  SSO 登录失败: {error_message}")
            return False

        print(f"  SSO 登录失败，收到未识别响应。HTTP状态码: {login_response.status_code}")
        print(f"  响应前200字符: {login_response.text[:200]}")
        return False

    def _normalize_ocr_text(self, text):
        """过滤 OCR 结果中的噪声字符，仅保留字母和数字。"""
        if text is None:
            return ""
        return re.sub(r"[^A-Za-z0-9]", "", str(text)).strip()

    def _image_to_png_bytes(self, image):
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _build_ocr_candidates(self, image_bytes):
        """
        为同一张验证码生成多种预处理版本，提升旧接口验证码的识别率。
        返回 [(label, image_bytes), ...]。
        """
        candidates = [("raw", image_bytes)]
        try:
            base = Image.open(io.BytesIO(image_bytes)).convert("L")
            autocontrast = ImageOps.autocontrast(base)
            enlarged = autocontrast.resize((base.width * 2, base.height * 2), Image.LANCZOS)
            threshold = autocontrast.point(lambda p: 255 if p > 150 else 0).convert("L")
            threshold_enlarged = enlarged.point(lambda p: 255 if p > 165 else 0).convert("L")

            derived = [
                ("autocontrast", autocontrast),
                ("enlarged", enlarged),
                ("threshold", threshold),
                ("threshold_enlarged", threshold_enlarged),
            ]
            for label, image in derived:
                candidates.append((label, self._image_to_png_bytes(image)))
        except Exception as e:
            print(f"    验证码图像预处理失败，回退到原图OCR: {e}")

        return candidates

    def _save_last_captcha_sample(self, reason):
        """保存最近一次验证码图片，便于人工核对 OCR 是否失准。"""
        if not self._last_captcha_bytes:
            return None

        os.makedirs(self._captcha_debug_dir, exist_ok=True)
        safe_reason = re.sub(r"[^A-Za-z0-9_-]", "_", reason)[:40] or "unknown"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = os.path.join(self._captcha_debug_dir, f"{timestamp}_{safe_reason}.jpg")
        with open(output_path, "wb") as f:
            f.write(self._last_captcha_bytes)
        return output_path

    def _get_captcha_and_ocr(self, max_ocr_retries=3):
        """
        获取验证码图片并进行OCR识别。
        返回 (verify_code, success) 元组。
        """
        for ocr_attempt in range(1, max_ocr_retries + 1):
            try:
                print(f"    获取验证码图片 (OCR尝试 {ocr_attempt}/{max_ocr_retries})...")
                captcha_url = f"{self.base_url}/yzm?d=1"
                captcha_response = self._request("GET", captcha_url, timeout=10)
                captcha_response.raise_for_status()
                self._last_captcha_bytes = captcha_response.content
                self._last_captcha_note = None

                print("    正在进行OCR识别...")
                candidates = self._build_ocr_candidates(captcha_response.content)
                observed_results = []
                for label, candidate_bytes in candidates:
                    raw_result = self.ocr.classification(candidate_bytes)
                    verify_code = self._normalize_ocr_text(raw_result)
                    observed_results.append(f"{label}:{raw_result}->{verify_code}")
                    if len(verify_code) == 4:
                        print(f"    OCR 识别成功 ({label}): {verify_code}")
                        return verify_code, True

                print("    验证码识别失败，未得到4位字母数字结果。")
                print(f"    OCR 候选结果: {' | '.join(observed_results)}")
                saved_path = self._save_last_captcha_sample("ocr_failed")
                if saved_path:
                    self._last_captcha_note = saved_path
                    print(f"    已保存失败验证码样本: {saved_path}")
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
        self._probe_login_environment()
        if self._use_sso_login:
            return self._login_via_sso(account, password)

        if not self._legacy_login_allowed:
            print("当前适配器已禁用旧教务登录链路。")
            return False

        max_login_retries = 3
        for login_attempt in range(1, max_login_retries + 1):
            print(f"  登录尝试 {login_attempt}/{max_login_retries}...")
            
            # 1. 获取验证码和OCR识别
            verify_code, ocr_success = self._get_captcha_and_ocr()
            if not ocr_success:
                print(f"  第 {login_attempt} 次登录尝试：验证码OCR识别连续失败。")
                if self._last_captcha_note:
                    print(f"  最近失败验证码样本已保存至: {self._last_captcha_note}")
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
                login_response = self._request("POST", login_url, data=login_data, timeout=10)
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
                        print(f"  登录失败: 验证码错误。OCR 结果可能失准，或旧接口校验规则已调整。")
                        saved_path = self._save_last_captcha_sample("captcha_rejected")
                        if saved_path:
                            self._last_captcha_note = saved_path
                            print(f"  本次被拒绝的验证码样本已保存至: {saved_path}")
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
                main_page_url = f"{self.base_url}/login!welcome.action"
                data_url = f"{self.base_url}/xsgrkbcx!getKbRq.action?xnxqdm={academic_year}&zc={week}"
                headers = self.headers.copy()
                headers['Referer'] = main_page_url
                print(f"  获取课表数据 (尝试 {attempt}/{max_retries})...")
                response = self._request("GET", data_url, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"  获取课表数据失败，HTTP状态码: {response.status_code}")
                    if attempt < max_retries:
                        print("  等待2秒后重试...")
                        time.sleep(2)
                    continue # 重试

                response.raise_for_status() # 检查其他HTTP错误
                if response.text.lstrip().startswith("<!DOCTYPE") or "非法访问" in response.text:
                    print("  课表数据接口返回了非法访问页面，而不是周课表数据。")
                    if attempt < max_retries:
                        print("  等待2秒后重试...")
                        time.sleep(2)
                    continue
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
