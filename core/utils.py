# core/utils.py
from Crypto.Cipher import AES

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