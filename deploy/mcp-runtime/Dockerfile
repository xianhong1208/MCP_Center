# 受控基底 image:BYO(自帶啟動指令)MCP 的執行環境
#
# 內含:node(supergateway 依賴)、python + uv(uvx MCP)、supergateway(stdio↔HTTP 橋接)。
# orchestrator 以此 image 跑 container,command = supergateway --stdio "<內層 MCP 指令>"。
#
# 建置(有網路的機器):
#   docker build -t mcp-runtime:1 deploy/mcp-runtime
# 離線部署:save 出 tar → 目標主機 load 一次(平台一次性設定):
#   docker save -o mcp-runtime.tar mcp-runtime:1
#   # 目標主機:docker load -i mcp-runtime.tar
#
# node 24(現行 LTS):多個 MCP 套件(如 firecrawl-mcp 的相依
# @mendable/firecrawl-js)要求 node >= 22,用 20 會出現 EBADENGINE 警告;
# 且本專案實測 firecrawl-mcp 正常運作的環境即為 node 24。
#
# 版本以 tag pin;若升級請同步調整 src/orchestrator/launch_spec.MCP_RUNTIME_IMAGE
# 或設定環境變數 MCP_RUNTIME_IMAGE。
FROM node:24-slim

# python3 + uv(uvx),供 python 型 BYO MCP 使用;
# 另補常見系統工具:npm 生態的 MCP 常直接 shell out 呼叫它們
# (實例:@browsermcp/mcp 啟動時執行 `lsof -ti:PORT | xargs kill -9`,
#  slim image 沒有 lsof/kill 會導致該 MCP 啟動失敗)。
#   lsof   — 查佔用 port 的行程
#   procps — 提供 kill / ps / pgrep
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv curl ca-certificates lsof procps \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx

# supergateway:stdio ↔ HTTP(SSE)橋接;全域安裝,orchestrator 直接以 `supergateway` 呼叫
RUN npm install -g supergateway

# 非 root 執行(縱深防禦;BYO 內層指令由 supergateway 以此身分 spawn)
RUN useradd -m -u 10001 mcp
USER mcp
WORKDIR /home/mcp

# 無固定 ENTRYPOINT:實際 command 由 orchestrator 於 containers.run 帶入
#   ["supergateway", "--stdio", "<inner cmd>", "--port", "<port>", "--host", "0.0.0.0"]
