"""配置管理器

支援環境變數擴展:
- ${VAR_NAME}           必須設定的環境變數
- ${VAR_NAME:-default}  可選,有預設值
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from src.config.model import (
    ConfigModel,
    CORSConfig,
    DatabaseConfig,
    IdentityConfig,
    LoggingConfig,
    OAuthConfig,
    RateLimitConfig,
    SecurityConfig,
    ServerConfig,
    SessionConfig,
)

ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def expand_env_vars(value: Any) -> Any:
    """遞迴展開 ${VAR} / ${VAR:-default}。"""
    if isinstance(value, str):
        def replacer(match):
            var_name = match.group(1)
            default_value = match.group(2)
            env_value = os.environ.get(var_name)
            if env_value is not None:
                return env_value
            if default_value is not None:
                return default_value
            raise ValueError(
                f"Environment variable '{var_name}' is not set and has no default value. "
                f"Please set it or provide a default in config: ${{{var_name}:-default}}"
            )
        return ENV_VAR_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


class Config:
    """配置管理器(單例)。未呼叫 set_config 時提供內建預設值,方便測試與零設定啟動。"""

    _config_path: Optional[str] = None
    _config_model: Optional[ConfigModel] = None

    @classmethod
    def set_config(cls, config_path: str):
        cls._config_path = config_path
        cls._config_model = cls._load_config(config_path)

    @classmethod
    def set_model(cls, model: ConfigModel):
        """直接注入設定物件(測試用)。"""
        cls._config_path = None
        cls._config_model = model

    @classmethod
    def reset(cls):
        cls._config_path = None
        cls._config_model = None

    @classmethod
    def _load_config(cls, config_path: str) -> ConfigModel:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # `${PORT:-4568}` 展開後是字串;pydantic lax mode 會依欄位型別轉成 int / bool
        return ConfigModel(**expand_env_vars(raw))

    @classmethod
    def get_config_model(cls) -> ConfigModel:
        if cls._config_model is None:
            cls._config_model = ConfigModel()
        return cls._config_model

    @classmethod
    def get_database_config(cls) -> DatabaseConfig:
        return cls.get_config_model().database

    @classmethod
    def get_server_config(cls) -> ServerConfig:
        return cls.get_config_model().server

    @classmethod
    def get_session_config(cls) -> SessionConfig:
        return cls.get_config_model().session

    @classmethod
    def get_oauth_config(cls) -> OAuthConfig:
        return cls.get_config_model().oauth

    @classmethod
    def get_identity_config(cls) -> IdentityConfig:
        return cls.get_config_model().identity

    @classmethod
    def get_logging_config(cls) -> LoggingConfig:
        return cls.get_config_model().logging

    @classmethod
    def get_rate_limit_config(cls) -> RateLimitConfig:
        return cls.get_config_model().rate_limit

    @classmethod
    def get_security_config(cls) -> SecurityConfig:
        return cls.get_config_model().security

    @classmethod
    def get_cors_config(cls) -> CORSConfig:
        return cls.get_config_model().cors
