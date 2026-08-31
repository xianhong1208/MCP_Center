"""AES-256-GCM 靜態資料加密(私鑰、服務 token、容器 env)與 SHA-256 雜湊工具。

金鑰來源:ENCRYPTION_KEY 環境變數;未設定則由 secrets_store 自動產生並持久化。
"""

import base64
import hashlib
import os
from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class TokenCrypto:
    """AES-256-GCM 加密/解密。"""

    def __init__(self, secret_key: Optional[str] = None):
        if secret_key is None:
            from src.utils.secrets_store import get_secret
            secret_key = get_secret("ENCRYPTION_KEY")
        self.key = hashlib.sha256(secret_key.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return base64.b64encode(nonce + encryptor.tag + ciphertext).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        data = base64.b64decode(ciphertext)
        nonce, tag, encrypted = data[:12], data[12:28], data[28:]
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(nonce, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return (decryptor.update(encrypted) + decryptor.finalize()).decode()


_crypto_instance: Optional[TokenCrypto] = None


def get_crypto() -> TokenCrypto:
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = TokenCrypto()
    return _crypto_instance


def reset_crypto() -> None:
    """測試用:換金鑰後重建 singleton。"""
    global _crypto_instance
    _crypto_instance = None


def encrypt_token(token: str) -> str:
    return get_crypto().encrypt(token)


def decrypt_token(encrypted: str) -> str:
    return get_crypto().decrypt(encrypted)


def hash_token(token: str) -> str:
    """SHA-256 hex(用於 client secret / 授權碼等只需比對不需還原的值)。"""
    return hashlib.sha256(token.encode()).hexdigest()


def get_token_prefix(token: str, length: int = 8) -> str:
    return token[:length] if len(token) >= length else token
