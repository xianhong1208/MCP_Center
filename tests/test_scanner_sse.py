"""Scanner:Streamable HTTP 的 SSE 回應必須「增量讀」

背景(實測 firecrawl-mcp + supergateway 得到的結論):
Streamable HTTP 的回應常是 `text/event-stream` + chunked,且**連線保持開啟**。
先前 scanner 用 `response.read()/text()` 等整個 body 結束 —— 對 SSE 而言永遠
不會結束,結果是逾時、連線被中斷,對端(supergateway)還會在回寫時因找不到
連線而拋未捕捉例外整個崩潰,症狀就是服務永遠 offline、抓不到 tools。

本檔釘住:遇到不會結束的 SSE 串流,必須拿到第一則完整 JSON-RPC 訊息就返回。
"""
import asyncio
import json

import pytest

from src.discovery.scanner import MCPScanner


class _FakeContent:
    """模擬 aiohttp response.content:吐完指定 chunk 後**永不結束**(如同真實 SSE)。"""

    def __init__(self, chunks, hang_forever=True):
        self._chunks = list(chunks)
        self._hang = hang_forever

    async def iter_any(self):
        for c in self._chunks:
            yield c
        if self._hang:
            await asyncio.sleep(3600)  # 串流保持開啟 —— 若實作等 body 結束就會卡死


class _FakeResponse:
    def __init__(self, chunks, content_type="text/event-stream", json_body=None,
                 hang_forever=True):
        self.headers = {"Content-Type": content_type}
        self.content = _FakeContent(chunks, hang_forever)
        self._json_body = json_body

    async def json(self):
        return self._json_body


_MSG = {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "x", "version": "1"}}}


@pytest.mark.asyncio
async def test_sse_returns_before_stream_ends():
    """串流不會結束,但拿到第一則訊息就該返回(不可卡死)。"""
    chunks = [f"event: message\ndata: {json.dumps(_MSG)}\n\n".encode()]
    scanner = MCPScanner()
    got = await asyncio.wait_for(
        scanner._read_jsonrpc(_FakeResponse(chunks)), timeout=5,
    )
    assert got == _MSG


@pytest.mark.asyncio
async def test_sse_message_split_across_chunks():
    """一則訊息被切在多個 chunk 中間也要能組回來。"""
    payload = f"event: message\ndata: {json.dumps(_MSG)}\n\n"
    mid = len(payload) // 2
    chunks = [payload[:mid].encode(), payload[mid:].encode()]
    scanner = MCPScanner()
    got = await asyncio.wait_for(
        scanner._read_jsonrpc(_FakeResponse(chunks)), timeout=5,
    )
    assert got == _MSG


@pytest.mark.asyncio
async def test_sse_skips_non_data_lines():
    """SSE 的 event/id/註解行要略過,只取 data。"""
    chunks = [b": ping\nevent: message\nid: 7\n", f"data: {json.dumps(_MSG)}\n\n".encode()]
    scanner = MCPScanner()
    got = await asyncio.wait_for(
        scanner._read_jsonrpc(_FakeResponse(chunks)), timeout=5,
    )
    assert got == _MSG


@pytest.mark.asyncio
async def test_plain_json_response_still_works():
    """非 SSE(application/json)維持原本行為。"""
    scanner = MCPScanner()
    resp = _FakeResponse([], content_type="application/json", json_body=_MSG)
    got = await asyncio.wait_for(scanner._read_jsonrpc(resp), timeout=5)
    assert got == _MSG


@pytest.mark.asyncio
async def test_stream_ends_without_message_returns_none():
    """串流結束卻沒有可解析的訊息 → None(不可拋例外)。"""
    scanner = MCPScanner()
    resp = _FakeResponse([b": comment only\n\n"], hang_forever=False)
    got = await asyncio.wait_for(scanner._read_jsonrpc(resp), timeout=5)
    assert got is None
