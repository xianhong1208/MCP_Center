"""Managed MCP Orchestrator

職責:從 marketplace catalog 啟動 / 停止 / 監控 sibling container,
並管理 supergateway bridge subprocess。

架構摘要(見專案討論筆記):
  - MCP Center 以 --network host 跑
  - 透過 /var/run/docker.sock 啟動 Perplexity 等 stdio MCP 為 sibling
  - spawn supergateway Node.js subprocess 作為 stdio ↔ HTTP bridge
  - bridge 綁在 127.0.0.1:<port>,agent 直連,流量不經 MCP Center
"""

from src.orchestrator.port_allocator import PortAllocator, PortAllocationError

__all__ = ["PortAllocator", "PortAllocationError"]
