# core/utils.py
from Crypto.Cipher import AES
from datetime import datetime

def gdut_encrypt_password(password, key):
    """广东工业大学特定的AES/ECB/PKCS7Padding加密密码。"""
    key_bytes = key.encode('utf-8')
    password_bytes = password.encode('utf-8')
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    block_size = AES.block_size
    padding_len = block_size - (len(password_bytes) % block_size)
    padded_password = password_bytes + (chr(padding_len) * padding_len).encode('utf-8')
    encrypted_bytes = cipher.encrypt(padded_password)
    return encrypted_bytes.hex()

def get_current_academic_semester():
    """
    根据当前日期严格计算学年学期代码。
    - 每年2月-7月: 视为春季学期（第二学期），隶属于前一个学年。
    - 每年8月-12月: 视为秋季学期（第一学期），隶属于当前学年。
    - 每年1月: 视为秋季学期（第一学期）的期末，隶属于前一个学年。
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    if 2 <= current_month <= 7:
        # 当前是2月-7月，属于春季学期（第二学期）。
        # 学年是当前年份减一。
        academic_year = current_year - 1
        return f"{academic_year}02"
    elif current_month >= 8:
        # 当前是8月-12月，属于秋季学期（第一学期）。
        # 学年就是当前年份。
        academic_year = current_year
        return f"{academic_year}01"
    else:  # 此分支仅包含 current_month == 1 的情况
        # 当前是1月，属于上一学年秋季学期（第一学期）的结尾。
        # 学年是当前年份减一。
        academic_year = current_year - 1
        return f"{academic_year}01"
