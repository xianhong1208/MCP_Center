"""加密工具測試

測試涵蓋：
1. Token 加密/解密
2. 密鑰處理
"""

import pytest
import os


class TestTokenEncryption:
    """Token 加密解密測試"""

    def test_encrypt_decrypt_token(self):
        """測試加密和解密 Token"""
        # 設定測試用密鑰
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token, decrypt_token

        original_token = "my-secret-mcp-token-12345"

        # 加密
        encrypted = encrypt_token(original_token)
        assert encrypted != original_token
        assert len(encrypted) > 0

        # 解密
        decrypted = decrypt_token(encrypted)
        assert decrypted == original_token

    def test_encrypt_empty_token(self):
        """測試加密空 Token"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token

        encrypted = encrypt_token("")
        assert encrypted == ""

    def test_decrypt_empty_token(self):
        """測試解密空 Token"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import decrypt_token

        decrypted = decrypt_token("")
        assert decrypted == ""

    def test_encrypt_special_characters(self):
        """測試加密含特殊字元的 Token"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token, decrypt_token

        special_token = "token!@#$%^&*()_+-=[]{}|;':\",./<>?"

        encrypted = encrypt_token(special_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == special_token

    def test_different_tokens_different_ciphertext(self):
        """測試不同 Token 產生不同密文"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token

        token1 = "token-one"
        token2 = "token-two"

        encrypted1 = encrypt_token(token1)
        encrypted2 = encrypt_token(token2)

        assert encrypted1 != encrypted2

    def test_same_token_different_ciphertext_each_time(self):
        """測試相同 Token 每次加密產生不同密文（因為 IV 不同）"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token

        token = "same-token"

        encrypted1 = encrypt_token(token)
        encrypted2 = encrypt_token(token)

        # 由於使用隨機 IV，相同明文每次加密結果應該不同
        assert encrypted1 != encrypted2

    def test_long_token_encryption(self):
        """測試長 Token 加密"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token, decrypt_token

        long_token = "x" * 1000  # 1000 字元的 Token

        encrypted = encrypt_token(long_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == long_token

    def test_unicode_token_encryption(self):
        """測試 Unicode Token 加密"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from src.utils.crypto import encrypt_token, decrypt_token

        unicode_token = "密碼Token🔐中文"

        encrypted = encrypt_token(unicode_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == unicode_token


class TestKeyDerivation:
    """密鑰派生測試"""

    def test_key_derivation_consistency(self):
        """測試密鑰派生一致性"""
        os.environ["SERVICE_TOKEN_SECRET"] = "consistent-secret-key!!"

        from src.utils.crypto import encrypt_token, decrypt_token

        token = "test-token"
        encrypted = encrypt_token(token)

        # 使用相同密鑰應該能解密
        decrypted = decrypt_token(encrypted)
        assert decrypted == token

    def test_different_keys_cannot_decrypt(self):
        """測試不同密鑰無法解密"""
        os.environ["SERVICE_TOKEN_SECRET"] = "original-secret-key-32!!"

        from src.utils.crypto import encrypt_token

        token = "secret-data"
        encrypted = encrypt_token(token)

        # 改變密鑰
        os.environ["SERVICE_TOKEN_SECRET"] = "different-secret-key-32!"

        # 重新載入模組以使用新密鑰
        import importlib
        import src.utils.crypto as crypto_module
        importlib.reload(crypto_module)

        from src.utils.crypto import decrypt_token

        # 應該無法解密或返回錯誤結果
        try:
            decrypted = decrypt_token(encrypted)
            # 如果沒有拋出異常，檢查結果是否正確
            assert decrypted != token or decrypted is None
        except Exception:
            # 預期會失敗
            pass


class TestCryptoSpecCoverage:
    """補齊 SPEC-CRYPTO 需求缺口:竄改偵測、金鑰缺失、hash、前綴。

    以 TokenCrypto(secret_key=...) 直接建構,不走 singleton / 環境變數,
    達到測試隔離(對應 SPEC-CRYPTO 第 5 節)。
    """

    def test_tampered_ciphertext_rejected(self):
        """TC-CRYPTO-03 / REQ-CRYPTO-03:竄改密文須被拒,不得回錯誤明文"""
        from src.utils.crypto import TokenCrypto

        crypto = TokenCrypto(secret_key="unit-test-secret-A")
        cipher = crypto.encrypt("my-secret-token-123")

        # 竄改末位字元(base64),破壞 GCM tag / 內容
        tampered = cipher[:-2] + ("AA" if cipher[-2:] != "AA" else "BB")

        with pytest.raises(Exception):
            crypto.decrypt(tampered)

    def test_missing_secret_is_generated_and_persisted(self, monkeypatch, tmp_path):
        """無 ENCRYPTION_KEY 時由 secrets store 自動產生並持久化,之後每次都拿同一把"""
        from src.utils import secrets_store
        from src.utils.crypto import TokenCrypto

        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("MCP_CENTER_SECRETS_FILE", str(tmp_path / "secrets.json"))
        secrets_store.reset_cache()
        first = TokenCrypto()
        secrets_store.reset_cache()
        second = TokenCrypto()
        assert first.key == second.key
        assert (tmp_path / "secrets.json").exists()
        assert second.decrypt(first.encrypt("hello")) == "hello"

    def test_wrong_key_cannot_decrypt(self):
        """TC-CRYPTO-05 / REQ-CRYPTO-05:不同金鑰不可互解(強化既有測試)"""
        from src.utils.crypto import TokenCrypto

        a = TokenCrypto(secret_key="key-A-unit-test")
        b = TokenCrypto(secret_key="key-B-unit-test")
        cipher = a.encrypt("cross-key-secret")

        with pytest.raises(Exception):
            b.decrypt(cipher)

    def test_hash_token_stable_and_unique(self):
        """TC-CRYPTO-06 / REQ-CRYPTO-06:hash_token 穩定、64 位十六進位、唯一"""
        from src.utils.crypto import hash_token

        h1 = hash_token("token-a")
        h1_again = hash_token("token-a")
        h2 = hash_token("token-b")

        assert h1 == h1_again                      # 穩定
        assert len(h1) == 64                        # SHA-256 十六進位
        assert all(c in "0123456789abcdef" for c in h1)
        assert h1 != h2                             # 唯一

    def test_get_token_prefix(self):
        """TC-CRYPTO-07 / REQ-CRYPTO-07:取前綴;不足長度回原字串"""
        from src.utils.crypto import get_token_prefix

        assert get_token_prefix("abcdef12345") == "abcdef12"   # 前 8 字元
        assert get_token_prefix("abc") == "abc"                 # 長度不足回原字串
        assert get_token_prefix("abcdef12345", length=4) == "abcd"


class TestServiceTokenInDatabase:
    """服務 Token 在資料庫中的加密測試"""

    def test_service_auth_token_stored_encrypted(self, db_session):
        """測試服務 Auth Token 以加密形式儲存"""
        os.environ["SERVICE_TOKEN_SECRET"] = "test-secret-key-32-chars-long!!"

        from db.crud import ServiceCRUD
        from src.utils.crypto import encrypt_token, decrypt_token

        original_token = "my-mcp-auth-token"
        encrypted_token = encrypt_token(original_token)

        service = ServiceCRUD.create(
            db=db_session,
            name="encrypted-token-service",
            host="localhost",
            port=9100,
            auth_token_encrypted=encrypted_token,
        )

        # 從資料庫取得
        fetched = ServiceCRUD.get_by_id(db_session, str(service.id))

        # 儲存的應該是加密後的值
        assert fetched.auth_token_encrypted == encrypted_token
        assert fetched.auth_token_encrypted != original_token

        # 解密應該得到原始值
        decrypted = decrypt_token(fetched.auth_token_encrypted)
        assert decrypted == original_token
