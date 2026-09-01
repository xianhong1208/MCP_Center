"""Docker argv 安全政策(單一來源)

這個模組定義「什麼樣的 token 可以進到 `docker run` 的 argv」,並被**兩個
邊界**共用:

  1. 寫入邊界 — src/marketplace/schema.py 的 DockerSpec:
     catalog YAML 載入時驗證,壞掉的 entry 直接不會被 install。
  2. 執行邊界 — src/orchestrator/manager.py 的 _start_locked:
     從 DB 讀出 image_args / image_command 之後、組 argv 之前再驗一次。

為什麼兩邊都要驗(不是多餘):

  * 這是 **Stored** command/argument injection。威脅模型包含「攻擊者已經有
    辦法寫 DB」(SQL injection、洩漏的 DB 憑證、內部誤用 CRUD)。那條路徑
    完全繞過 catalog,所以只在寫入時驗等於沒防。
  * 靜態掃描(SAST 工具)無法把「寫進 DB 前驗過」和「從 DB 讀出來用」
    連起來 — 這是 stored flow 的本質限制。sanitizer 必須出現在 DB 讀取與
    subprocess 之間,才是真的在那條路徑上。

政策的核心取捨:`args` 用 **flag 層級**白名單,不是字元層級。
`-v /:/host`、`--privileged`、`--pid=host` 全由「安全字元」組成,任何字元
白名單都放行,shlex.quote 也一樣(quote 管 shell 安全,不管 argv 語意)。
只有列舉允許的 flag 才能讓逃逸 flag「無法表達」。
"""
import re
from typing import Iterable, List

# 不帶值的 flag。刻意不收錄(= 一律拒絕)的逃逸向量:
#   -v/--volume/--mount  → 掛載 host 檔案系統
#   --privileged, --cap-add, --device, --security-opt, --userns → 提權
#   --pid/--ipc/--uts    → 共用 host namespace
#   --entrypoint         → 取代 image 進入點
#   -d/--detach          → orchestrator 自己決定 -i / -d,catalog 不得覆寫
_ALLOWED_BARE_FLAGS = frozenset({"--rm", "-i", "-t", "-it", "--init"})

# BYO(自帶啟動指令)允許的內層 command。刻意 default-deny:
# 只允許在受控基底 image 內存在、且由 supergateway spawn 的 runtime launcher。
# 不允許任意路徑/二進位(避免 `bash`、`sh -c`、絕對路徑執行檔等)。
_ALLOWED_BYO_COMMANDS = frozenset({"npx", "node", "uvx", "python", "python3"})

# 剛好帶一個值的 flag → 每個 flag 各自的值格式。
_ALLOWED_VALUE_FLAGS = {
    # host 刻意不放行:會拿掉網路隔離,讓 container 直接打到 host 上的
    # MCP Center admin API(127.0.0.1)。
    "--network": re.compile(r"(bridge|none)"),
    "--pull": re.compile(r"(always|missing|never)"),
    "--memory": re.compile(r"\d+[bkmg]?"),
    "--cpus": re.compile(r"\d+(\.\d+)?"),
}

# docker image name(不含 tag);可選的 registry host[:port] 前綴。
_IMAGE_RE = re.compile(
    r"(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?/)?"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"
)

# docker 自己的 tag 規則。
_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}")

# entrypoint args(docker.command)是傳給 *image* 的參數,不是 `docker run`
# 的 flag,因此造不成 container 逃逸 — 字元白名單在這裡是合適的強度。
_SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:=/@,+-]+")

# 注意:以下所有比對都用 `fullmatch`,不用 `match`。`$` 會在字串結尾的換行
# 之前就成立,所以 `match` 加 `^...$` 仍會放行 "--rm\n" 這種尾端換行的 token。


class ArgvPolicyError(ValueError):
    """token 不符合 docker argv 政策。

    繼承 ValueError,所以在 Pydantic field_validator 裡 raise 會被正常轉成
    ValidationError;在 orchestrator 裡則由呼叫端轉成 OrchestratorError。
    """


def validate_docker_args(tokens: Iterable[str]) -> List[str]:
    """驗證 `docker run` 的 flag 序列,回傳原序列(方便串接使用)。

    必須把 args 當**序列**走訪,不能逐 token 獨立檢查:docker flag 有
    `--network=bridge`(單 token)和 `--network bridge`(雙 token)兩種寫法,
    要判斷 `/:/host` 合不合法,得知道前一個 token 是不是 `-v`。

    不在白名單的 flag 一律拒絕(default-deny),所以 `-v`、`--privileged`
    這類逃逸 flag 是「無法表達」而非「被過濾掉」。
    """
    args = list(tokens)
    i = 0
    while i < len(args):
        token = args[i]

        if token in _ALLOWED_BARE_FLAGS:
            i += 1
            continue

        flag, sep, inline_value = token.partition("=")
        value_re = _ALLOWED_VALUE_FLAGS.get(flag)
        if value_re is None:
            raise ArgvPolicyError(
                f"不允許的 docker flag: {token!r}。"
                f"允許的 flag:{sorted(_ALLOWED_BARE_FLAGS)} "
                f"+ {sorted(_ALLOWED_VALUE_FLAGS)}"
            )

        if sep:
            # --flag=value 形式
            value = inline_value
            i += 1
        else:
            # --flag value 形式
            if i + 1 >= len(args):
                raise ArgvPolicyError(f"docker flag {flag!r} 缺少值")
            value = args[i + 1]
            i += 2

        if not value_re.fullmatch(value):
            raise ArgvPolicyError(
                f"docker flag {flag!r} 不允許此值: {value!r}"
            )

    return args


def validate_command_tokens(tokens: Iterable[str]) -> List[str]:
    """驗證 entrypoint args(docker.command),回傳原序列。

    這些 token 不會成為 `docker run` 的 flag,所以無法造成 container 逃逸;
    只需擋掉 shell metachar 與空白(空白還會破壞 image_args 的 join/split
    往返,見 orchestrator.manager)。
    """
    command = list(tokens)
    for token in command:
        if not isinstance(token, str) or not _SAFE_TOKEN_RE.fullmatch(token):
            raise ArgvPolicyError(f"entrypoint arg 含不安全字元: {token!r}")
    return command


def validate_byo_command(command: str) -> str:
    """驗證 BYO 內層 command(白名單 default-deny)。"""
    if command not in _ALLOWED_BYO_COMMANDS:
        raise ArgvPolicyError(
            f"不允許的 BYO command: {command!r}"
            f"(僅允許 {sorted(_ALLOWED_BYO_COMMANDS)})"
        )
    return command


def validate_byo_launch(command: str, args: Iterable[str]) -> tuple:
    """驗證 BYO 內層啟動指令:command 白名單 + args 字元白名單。

    args 沿用 `validate_command_tokens` 的字元白名單(`_SAFE_TOKEN_RE`),
    可擋 shell metachar(`; | & $ () 反引號`)與空白 —— 即使容器內 supergateway
    以 shell 解析內層指令,也無法被注入。args 最終以 **list** 傳給 docker SDK
    (無 shell),字元白名單是額外的縱深防禦。

    Returns:
        (command, validated_args_list)
    """
    cmd = validate_byo_command(command)
    validated_args = validate_command_tokens(args)
    return cmd, validated_args


def validate_image_name(image: str) -> str:
    """驗證 image name(不含 tag)。"""
    if not _IMAGE_RE.fullmatch(image):
        raise ArgvPolicyError(f"不是合法的 docker image name: {image!r}")
    return image


def validate_tag(tag: str) -> str:
    """驗證 image tag。"""
    if not _TAG_RE.fullmatch(tag):
        raise ArgvPolicyError(f"不是合法的 docker image tag: {tag!r}")
    return tag


def validate_image_ref(image_ref: str) -> str:
    """驗證從 DB 讀回來的完整 `image[:tag]`。

    切在最後一個 ':',但只有當該 ':' 在最後一個 '/' 之後才算 tag 分隔 —
    否則 `localhost:5000/img` 的 port 會被誤認成 tag。
    """
    head, sep, tail = image_ref.rpartition(":")
    if sep and "/" not in tail:
        validate_image_name(head)
        validate_tag(tail)
    else:
        validate_image_name(image_ref)
    return image_ref
