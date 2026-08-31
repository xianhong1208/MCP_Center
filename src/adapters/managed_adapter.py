"""Managed MCP / Tool 領域 Adapter

三層架構的中間層:API 只呼叫這裡的方法;adapter 負責「呼叫 db.crud + 業務邏輯」。
涵蓋 Managed MCP 程序與探索到的 MCP Tools。
"""

from db.crud import ManagedMcpProcessCRUD, MCPToolCRUD, UserMcpDefinitionCRUD
from src.adapters.exceptions import ConflictError, NotFoundError, ValidationFailedError


class MCPToolAdapter(MCPToolCRUD):
    """MCP Tool adapter。"""


class ManagedMcpProcessAdapter(ManagedMcpProcessCRUD):
    """Managed MCP process adapter。"""

    @classmethod
    def get_existing(cls, db, process_id):
        """取得既存 process;不存在 → NotFoundError(managed.process_not_found)。"""
        p = cls.get_by_id(db, process_id)
        if not p:
            raise NotFoundError(
                code="managed.process_not_found", fallback="Managed process not found",
            )
        return p

    @classmethod
    def assert_not_installed(cls, db, catalog_id):
        """single-instance 檢查:同 catalog 已安裝 → ConflictError(409)。"""
        existing = cls.list_all(db, catalog_id=catalog_id)
        if existing:
            existing_id = str(existing[0].id)
            raise ConflictError(
                code="managed.catalog_already_installed",
                params={"catalog_id": catalog_id, "process_id": existing_id},
                fallback=(
                    f"Catalog '{catalog_id}' is already installed "
                    f"(process_id={existing_id}). Single-instance policy."
                ),
            )

    @classmethod
    def purge_with_service(cls, db, process, logger) -> None:
        """uninstall 的資料清理:刪關聯 Service(含事件紀錄)+ process row。

        (orchestrator stop 由呼叫端先行;此處只負責 DB 資料鏈。)
        """
        from src.adapters.service_adapter import ServiceAdapter

        associated_service_id = str(process.service_id) if process.service_id else None
        if associated_service_id:
            try:
                ServiceAdapter.delete(db, associated_service_id)
            except Exception as e:
                logger.warning(f"Service cleanup during uninstall: {e}")
        cls.delete(db, str(process.id))


class BYODefinitionAdapter(UserMcpDefinitionCRUD):
    """使用者自帶(BYO)MCP 定義 adapter。

    建立時套 argv 政策(command 白名單 + args 字元白名單);刪除前擋「已部署」。
    """

    @classmethod
    def create_definition(
        cls, db, *, name, command, args=None, container_port=8000,
        env_schema=None, description=None, created_by_id=None,
    ):
        """驗證 + 建立 BYO 定義。

        - command/args 不合政策 → ValidationFailedError(400)
        - name 重複 → ConflictError(409)
        """
        from src.marketplace.argv_policy import ArgvPolicyError, validate_byo_launch

        try:
            validated_cmd, validated_args = validate_byo_launch(command, args or [])
        except ArgvPolicyError as e:
            raise ValidationFailedError(
                code="byo.invalid_command",
                params={"reason": str(e)},
                fallback=f"Invalid BYO launch command: {e}",
            )
        try:
            return cls.create(
                db, name=name, command=validated_cmd, args=validated_args,
                container_port=container_port, env_schema=env_schema,
                description=description, created_by_id=created_by_id,
            )
        except ValueError:
            raise ConflictError(
                code="byo.name_exists",
                params={"name": name},
                fallback=f"MCP definition '{name}' already exists",
            )

    @classmethod
    def get_existing(cls, db, definition_id):
        """取得既存定義;不存在 → NotFoundError(404)。"""
        d = cls.get_by_id(db, definition_id)
        if not d:
            raise NotFoundError(
                code="byo.definition_not_found", fallback="BYO MCP definition not found",
            )
        return d

    @classmethod
    def delete_guarded(cls, db, definition_id):
        """刪除定義;已部署(存在對應 managed process)→ ConflictError(409)。"""
        from src.orchestrator.launch_spec import user_source_id

        d = cls.get_existing(db, definition_id)
        deployed = ManagedMcpProcessAdapter.list_all(
            db, catalog_id=user_source_id(str(d.id))
        )
        if deployed:
            raise ConflictError(
                code="byo.definition_in_use",
                params={"process_id": str(deployed[0].id)},
                fallback="Definition is deployed; uninstall the process first.",
            )
        cls.delete(db, definition_id)
