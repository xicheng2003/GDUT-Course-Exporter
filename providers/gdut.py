# providers/gdut.py
from core.utils import gdut_encrypt_password

GDUT_PROVIDER = {
    "name": "广东工业大学",
    "base_url": "https://jxfw.gdut.edu.cn",
    "sso_login_url": "https://authserver.gdut.edu.cn/authserver/login",
    "sso_service_url": "https://jxfw.gdut.edu.cn/new/ssoLogin",
    "allow_insecure_ssl_fallback": True,
    "encrypt_password_func": gdut_encrypt_password,
    "class_time_map": {
        "01": ("08:30", "09:15"), "02": ("09:20", "10:05"), "03": ("10:25", "11:10"),
        "04": ("11:15", "12:00"), "05": ("13:50", "14:35"), "06": ("14:40", "15:25"),
        "07": ("15:30", "16:15"), "08": ("16:30", "17:15"), "09": ("17:20", "18:05"),
        "10": ("18:30", "19:15"), "11": ("19:20", "20:05"), "12": ("20:10", "20:55"),
    }
}
