# 設計文件:自帶啟動指令的 MCP(BYO MCP Launch)

> **歷史設計文件**:寫於 RBAC 尚存在的版本,保留作為決策紀錄。與 1.0.0 實作不同之處:
>
> | 文中 | 1.0.0 實作 |
> |---|---|
> | `super_admin` / `managed:byo` 權限 | 已移除;所有登入的管理員都能建立、部署 BYO 定義 |
> | `/auth/byo-mcp*`、`/auth/managed` | `/api/byo-mcp`、`/api/byo-mcp/{id}`、`/api/byo-mcp/{id}/deploy`、`/api/managed` |
> | 基底 image `node:20-alpine` / `python:3.12-slim` | 單一受控 image `mcp-runtime:1`(`deploy/mcp-runtime/Dockerfile`,可用 `MCP_RUNTIME_IMAGE` 覆寫) |
> | Service 成員(owner / viewer) | 已移除(單租戶) |
> | Checkmarx | 指企業時期的 SAST 掃描 |

> 狀態:**已實作 v2**(P1–P6 完成;決策 Q1=不支援掛載起步、Q2=打包成 image、Q3=全做)
> 日期:2026-08-26
> 相關:三層架構重構、Marketplace 離線兩階段、Checkmarx SAST 加固

## ⚙️ 平台前置(部署前一次性設定)

BYO 部署會在**受控基底 image `mcp-runtime:1`**(node + python + uv + supergateway)內執行。
部署前需先建置並(離線)載入此 image:

```bash
docker build -t mcp-runtime:1 deploy/mcp-runtime
# 離線:docker save -o mcp-runtime.tar mcp-runtime:1 → 目標主機 docker load -i mcp-runtime.tar
```

image tag 可用環境變數 `MCP_RUNTIME_IMAGE` 覆寫。若此 image 不存在,deploy 會建立
process 但 start 失敗(actual_state=failed,last_error 明示)。

## ✅ 實作狀態

| 階段 | 產出 | 測試 |
|------|------|------|
| P1 | `user_mcp_definitions` 表 + migration + `LaunchSpec`/resolver | 7 |
| P2 | argv_policy:command 白名單 + `validate_byo_launch` | +5 |
| P3 | orchestrator stdio 分支(容器化 supergateway) | +2 |
| P4 | `BYODefinitionAdapter` + BYO API(三層) | +8 |
| P5 | 前端「自訂 MCP」表單 + `byoApi` | build ✅ |
| P6 | 全套 922 passed + 真實 server smoke(建立/列出/壞command 400/部署/擋刪 409) | ✅ |

---

---

## 1. 核心模型(一句話)

管理員**貼一份標準 stdio MCP 設定**(Claude Desktop / `mcp.json` 的 `{command, args, env}` 格式),
MCP Center 把它**在 container 內跑起來**,用 **supergateway 把 stdio 橋成 HTTP**,
**導出一個 `127.0.0.1:port`**,註冊成 MCP Center 裡的一個 Service(健康檢查 / token / 成員照舊)。

```
輸入(貼設定):
  { "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    "env":  { ... } }
        │
        ▼  MCP Center 在受控 container 內執行:
  ┌─ node 基底 container ──────────────┐   stdio   ┌─ supergateway ─┐
  │ npx -y @mcp/server-filesystem /data│◄────────►│ stdio ↔ HTTP    │──► 127.0.0.1:8123
  └────────────────────────────────────┘          └─────────────────┘
        │
        ▼  導出 127.0.0.1:8123 → 註冊成 Service(token / 健康檢查 / 成員照舊)
```

> 本質 = **復原先前為 Checkmarx 移除的 supergateway bridge 路徑**,再加一個「貼設定」入口;
> 並把橋接器與指令都關進 container(比舊版更安全)。

---

## 2. 已定案的決策

| # | 決策 | 值 |
|---|------|----|
| D1 | 誰能新增 BYO MCP | **僅 super_admin**(新權限 `managed:byo`) |
| D2 | 指令在哪裡執行 | **container 內**(受控基底 image;不在主機直跑) |
| D3 | 導出 port 綁哪 | **`127.0.0.1`**(只有 MCP Center 本機連得到,經其代理 + 發 token) |

---

## 3. 輸入格式與 kind 判定

使用者只需貼標準 `{command, args, env}`。MCP Center 依 `command` 決定用哪個受控基底 image:

| command | 基底 image(平台維護、pin 版本) | 實際容器內執行 |
|---------|-------------------------------|----------------|
| `npx` | `node:20-alpine` | `npx <args...>` |
| `node` | `node:20-alpine` | `node <args...>` |
| `uvx` | `python:3.12-slim`(預裝 `uv`) | `uvx <args...>` |
| `python` / `python3` | `python:3.12-slim` | `python <args...>` |
| (docker image) | 使用者指定 image | image entrypoint + args |

- 基底 image **由平台鎖定**,使用者不能指定 `node` 的來源 image(避免 `FROM 惡意image`)。
- `command` 只允許上述白名單值(default-deny);未列的一律拒。
- 也保留「直接給 docker image」的進階選項(等同現有 catalog 的 docker-http/docker-stdio)。

---

## 4. 執行:container + 容器化 supergateway

- **一切都在 container 內**(D2)。npx/uvx 也是 —— 塞進受控基底 image,獲得隔離、資源限制、網路限制。
- **supergateway 是容器化的 sibling container**(不再是 host `subprocess.Popen`):
  → 這**消除**了當初 Checkmarx 標記、被我移除的 subprocess sink,同時把橋接器也關進容器。
- 全程 **docker SDK**(`containers.run(command=[list])` / `images.load`),**零 CLI、零 shell**。
- 導出 port **綁 `127.0.0.1`**(D3),只有 MCP Center 本機連得到。

> **這一步同時回答「當初為何移除 stdio」**:當時是 host subprocess + 無 catalog 使用而移除;
> 現在改成容器化橋接 + 有明確需求,兩個顧慮都不成立。

---

## 5. 現有基礎(利多:多數骨架還在)

- DB 模型 `ManagedMcpProcess` 仍保留:`bridge_type`(預設 `supergateway`)、`bridge_container_id`、
  `container_id`、`port` / `auto_port`、`desired_state` / `actual_state`。
- schema `DockerSpec.transport` 仍有 `stdio`(「stdio = 需要 supergateway bridge」)。
- `port_allocator` 仍在。
- **只有 orchestrator 的 stdio 執行分支**在 Checkmarx 加固時被移除 → 本設計主要是**復原並容器化**它。

---

## 6. 資料模型

BYO 定義由使用者 runtime 產生,不能寫進 repo(catalog 是檔案)。新增一張表:

```
user_mcp_definitions
  id          UUID PK
  name        str
  command     str          # npx | node | uvx | python | (docker image 走另一組欄位)
  args_json   Text         # 驗證過的 args list
  env_schema  Text         # env vars 定義(哪些必填/secret)
  base_image  str          # 平台依 command 決定並快照(node:20-alpine ...)
  created_by  UUID FK admin_users
  created_at  datetime
```

- `ManagedMcpProcess.catalog_id` 語意擴充:可為「檔案 catalog id」或「`user:<uuid>`」。
- 定義一個 `LaunchSpec` 抽象(catalog YAML 與 user definition 都轉成它);orchestrator 只認 `LaunchSpec`。
- 好處:BYO 定義可重用、可稽核、可刪(符合 super_admin 高權限操作應留痕的原則)。

---

## 7. 安全控制矩陣

| 威脅 / 控制 | 機制 | 現況 |
|------------|------|------|
| 誰能建 | `managed:byo`,限 super_admin | 需新增 |
| 逃逸旗標(`-v` / `--privileged` / `--network host` ...) | argv **flag 白名單** default-deny | 已存在,延伸 |
| container 打 admin API | `--network` 限 bridge/none,禁 host | 已存在 |
| 資源耗盡 | `--memory` / `--cpus` 白名單 | 已存在 |
| command 白名單(npx/node/uvx/python) | fullmatch 列舉 | 需新增 |
| npx/uvx 套件名 + 版本 | fullmatch 字元白名單(§8) | 需新增 |
| stored injection(攻擊者已能寫 DB) | 寫入 + 執行邊界雙重驗證 | 已存在(沿用) |
| 稽核 | 每次 BYO 建立/啟停寫 audit + 指令快照 | 需新增 |
| SAST | docker SDK `command=[list]`,無 shell/subprocess | 已存在 |
| 導出面 | port 綁 127.0.0.1 | D3 |

---

## 8. command / 套件名驗證

- **command**:只允許 `npx` / `node` / `uvx` / `python` / `python3`(或 docker image 分支)。
- **args**:字元白名單 `fullmatch`(沿用 `_SAFE_TOKEN_RE`),禁 `;` `|` `&` 空白 `$()` 反引號。
- **npx 套件名**:`(@[a-z0-9-]+/)?[a-z0-9][a-z0-9._-]*`;版本 `[A-Za-z0-9._-]+`。
- **uvx 套件名**:PEP 508 名稱;版本同上。
- args 以 **list** 傳給 docker SDK(不拼 shell 字串)→ 即使驗證有漏也非 shell injection。

---

## 9. 主機路徑存取(container 隔離的取捨)← **唯一新開放問題**

你的範例 `.../server-filesystem` 帶主機路徑 `/data`、`/Users/.../Desktop`。
選了 **container 隔離(D2)** 後,container **預設看不到主機檔案系統**。
filesystem 這類需要存取主機目錄的 MCP,需要一條**受控 volume 掛載**:

**選項(待拍板,見 §16 Q1):**
1. **不支援主機掛載**:BYO MCP 一律無主機檔案存取。filesystem 型不適用(可用時再議)。最安全、最簡單。
2. **受控掛載白名單**:只允許掛載某約定根目錄(如 `/srv/mcp-shared`)底下的路徑,
   以唯讀為預設;argv 政策開一條**受控例外**(只放行白名單根目錄下的 `-v`,其餘照禁)。
   filesystem MCP 可用,但工程量與風險略增。

> 建議:**選項 1 起步**(先不支援主機掛載,涵蓋 perplexity/text2image 這類無檔案存取的 MCP);
> 待確有 filesystem 需求,再加選項 2 的受控白名單。

---

## 10. 離線環境的 npx/uvx 限制

本部署離線(image 靠 `docker load`)。`npx -y @foo/bar` runtime 會去 npm registry 下載,
離線連不到會失敗;uvx 對 pypi 同理。

**選項(待拍板,見 §16 Q2):**
1. npx/uvx 僅限有對外網路的部署;離線環境只用「docker image(tar 預載)」。UI 明示。
2. 內部 npm/pypi proxy(Verdaccio / devpi)。工程量大。
3. npx MCP 在有網路機器打包成 image → `docker save` → 離線 `docker load`(退化成 docker image 型)。

> 建議:**離線走選項 3**,與 marketplace 離線兩階段一致,不維護內部 registry。

---

## 11. 三層架構落點

- **`BYODefinitionAdapter`**(新):`create_definition`(驗證 + 存 DB)、`get`/`list`/`delete`;
  驗證失敗 → `ValidationFailedError`,重名 → `ConflictError`。
- **`ManagedMcpProcessAdapter`**:部署來源改吃 `LaunchSpec`(catalog 或 user definition 皆可)。
- **orchestrator**:復原/新增 stdio 分支(容器化 supergateway),docker SDK 全程。
- route 只收 request → 呼叫 adapter → 翻 domain 例外 → audit(維持本次重構的分層)。

---

## 12. API(草案)

| 端點 | 權限 | 說明 |
|------|------|------|
| `POST /auth/byo-mcp` | `managed:byo` | 貼設定 → 驗證 + 存定義,回 id |
| `GET /auth/byo-mcp` | `managed:byo` | 列出 BYO 定義 |
| `DELETE /auth/byo-mcp/{id}` | `managed:byo` | 刪定義(未部署才可刪) |
| `POST /auth/managed`(擴充) | `managed:install` | `source` 可為 `catalog:<id>` 或 `user:<uuid>` |

start / stop / uninstall 沿用現有 managed 端點。

---

## 13. 前端 UX

- Marketplace 新增「**+ 自訂 MCP**」入口(僅 super_admin 可見)。
- 表單直接接受**貼上 `{command, args, env}` JSON**(Claude Desktop 格式,降低學習成本)
  或以欄位填 command / args / env。
- 建立後出現在清單、標「自訂」badge,走與 catalog 相同的**部署 → 啟停**流程。
- 離線環境對 npx/uvx 顯示提示(§10)。

---

## 14. 對 Checkmarx / SAST 的影響

- 全走 docker SDK `containers.run(command=[list])` + `images.load` → 無 shell、無 subprocess。
- supergateway 由 host subprocess 改容器 → **消除**當初標記的 subprocess sink。
- 使用者輸入在**執行邊界**經 argv_policy `fullmatch` 白名單過濾(sanitizer 落在 DB 讀取與 docker SDK 之間)。
- 預期**不新增 Critical/High**;殘留風險是「授權的任意 container」(設計上接受),非注入漏洞。

---

## 15. 分階段實作計畫

| 階段 | 內容 |
|------|------|
| P0 | 本設計 v2 審核 + 拍板 §16 |
| P1 | `LaunchSpec` 抽象 + `user_mcp_definitions` 表 + migration |
| P2 | command/套件名驗證擴充(argv_policy)+ 單元測試 |
| P3 | orchestrator 復原 stdio 分支(容器化 supergateway)+ 127.0.0.1 導出 |
| P4 | `BYODefinitionAdapter` + BYO API(三層)+ 測試 |
| P5 | 前端自訂表單 + 部署整合 |
| P6 | 整合測試(mock docker)+ 實機 smoke + 文件 |

每階段獨立 commit + 測試綠。

---

## 16. 待你拍板

- **Q1 主機路徑存取**(§9):選項 1(先不支援掛載,最簡單安全)還是選項 2(受控掛載白名單,filesystem MCP 可用)?
  → 建議選項 1 起步。
- **Q2 離線 npx/uvx**(§10):選項 1/2/3?→ 建議選項 3(打包成 image)。
- **Q3 範圍**:P1–P6 全做,還是先 P1–P4(後端 + API)讓你用 API 先驗,前端(P5)另排?
