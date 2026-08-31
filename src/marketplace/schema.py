"""Marketplace catalog Pydantic schema

每個 catalog/*.yaml 檔對應一個 CatalogEntry,描述一個可從 MCP Center
UI 安裝的 MCP 服務模板。廠商看到的「Install」表單是從這個 schema
動態生成的。

設計原則:
  - extra='forbid' — 不認得的欄位直接報錯,避免廠商打錯字段名靜默失敗
  - secret + required 標記由 UI 決定欄位渲染方式(password / plain input)
  - docker.tag 應由我們 pin 住驗證過的版本,不建議用 latest 出貨
"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# docker argv 政策的單一來源。同一份規則也在 orchestrator 從 DB 讀出
# image_args / image_command 之後再套一次 — 見 argv_policy 的 module docstring
# 說明為什麼兩個邊界都要驗(Stored injection 的威脅模型 + SAST 的可見性)。
from src.marketplace.argv_policy import (
    validate_command_tokens,
    validate_docker_args,
    validate_image_name,
    validate_tag,
)


class EnvVarDef(BaseModel):
    """一個環境變數的定義 - 廠商 Install 時填一欄"""
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., description="Env var key, e.g. PERPLEXITY_API_KEY")
    label: str = Field(..., description="UI 顯示的 label")
    help: Optional[str] = Field(None, description="Help text;可放 URL")
    required: bool = True
    secret: bool = Field(
        False,
        description="True → UI 用 password input,後端加密存",
    )
    default: Optional[str] = Field(
        None,
        description="預設值;若 secret=True 建議勿設",
    )
    pattern: Optional[str] = Field(
        None,
        description="Regex 驗證;UI 與後端都會驗",
    )
    error_message: Optional[str] = Field(
        None,
        description="Regex 驗證失敗時顯示的訊息",
    )


class DockerSpec(BaseModel):
    """Container 啟動設定"""
    model_config = ConfigDict(extra='forbid')

    image: str = Field(..., description="e.g. mcp/perplexity-ask")
    tag: str = Field("latest", description="建議 pin 特定版本")
    args: List[str] = Field(
        default_factory=lambda: ["--rm"],
        description="docker run args",
    )
    transport: str = Field(
        "http",
        description="stdio = 需要 supergateway bridge; http = image 自帶 HTTP server",
    )
    container_port: int = Field(
        8080,
        description="HTTP 模式下 container 內部 listen 的 port (用於 -p mapping)",
    )
    command: List[str] = Field(
        default_factory=list,
        description="entrypoint args 接在 image_ref 之後 (e.g. ['--config','/app/cfg.yaml'])",
    )

    # 以下 validator 全部委派給 src/marketplace/argv_policy — 政策只有一份,
    # orchestrator 在執行邊界套用的是同樣的規則。

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v: str) -> str:
        return validate_image_name(v)

    @field_validator("tag")
    @classmethod
    def _validate_tag(cls, v: str) -> str:
        """tag 會被接成 `image:tag` 存進 DB,同樣要驗(先前完全沒驗)。"""
        return validate_tag(v)

    @field_validator("args")
    @classmethod
    def _validate_args(cls, v: List[str]) -> List[str]:
        """flag 層級白名單(預設拒絕)。字元白名單擋不住 -v /:/host。"""
        return validate_docker_args(v)

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: List[str]) -> List[str]:
        """entrypoint args:不是 docker flag,字元白名單即足夠。"""
        return validate_command_tokens(v)


class CatalogEntry(BaseModel):
    """單一 Marketplace 項目"""
    model_config = ConfigDict(extra='forbid')

    id: str = Field(..., description="唯一 ID,也是 catalog 檔名 (無 .yaml)")
    name: str = Field(..., description="UI 顯示名稱")
    description: str
    category: str = "general"
    icon: Optional[str] = Field(
        None,
        description="static/marketplace-icons/ 下的檔名 (optional)",
    )

    docker: DockerSpec
    env_vars: List[EnvVarDef] = Field(default_factory=list)

    docs_url: Optional[str] = None

    # 離線安裝:image tar 檔名(位於 catalog 目錄的 images/ 下)。
    # 未指定時採約定 `<id>.tar`。「安裝」= 後端以 docker SDK load 此 tar;
    # 「部署」= 啟動 container(image 必須已安裝)。
    image_tar: Optional[str] = Field(
        None,
        description=(
            "images/ 下的 tar 檔名;預設約定 <id>.tar。"
            "可用佔位符 {tag} / {image} / {id},例如 mit2i_{tag}.tar.gz —— "
            "升版時只需改 docker.tag,檔名自動跟著變。"
        ),
    )

    def image_tar_name(self) -> str:
        """解析 image tar 檔名。

        顯式指定優先,否則約定 <id>.tar。支援 {tag} / {image} / {id} 佔位符,
        讓檔名由 docker.tag 推導 —— 只保留一個事實來源,升版不必改兩處。
        image 可能含 registry 路徑(a/b/c),放進檔名時把 / 換成 _。
        """
        template = self.image_tar or f"{self.id}.tar"
        try:
            return template.format(
                id=self.id,
                image=self.docker.image.replace("/", "_"),
                tag=self.docker.tag,
            )
        except (KeyError, IndexError) as e:
            raise ValueError(
                f"image_tar 含未知佔位符 {e}(僅支援 {{tag}} {{image}} {{id}}): {template!r}"
            ) from e

    @model_validator(mode="after")
    def _validate_image_tar_template(self):
        """佔位符寫錯要在 yaml 載入時就報錯(loader 會略過壞 entry),
        而不是等市集列表被打時才在 image_tar_name() 炸出 500。"""
        self.image_tar_name()
        return self

    def public_dict(self) -> dict:
        """給 API 回傳給前端用;目前等同 model_dump(),未來若要隱藏內部
        欄位可在此調整"""
        return self.model_dump()
