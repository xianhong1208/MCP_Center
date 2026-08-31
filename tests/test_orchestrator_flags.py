"""Orchestrator — docker flag → docker SDK kwargs 轉換測試

_start_locked 已改用 docker SDK(取代 shell out `docker` CLI),消除 command
injection sink(Checkmarx: Stored Command Injection)。argv_policy 驗過的 flag
序列會經 _flags_to_kwargs 轉成 containers.run/create 的 kwargs;本檔釘住這層
對照的正確性(封閉白名單,對照唯一)。
"""
import pytest

from src.orchestrator.manager import _flags_to_kwargs


@pytest.mark.parametrize("flags, expected_kwargs, expected_pull", [
    ([], {}, False),
    (["--rm"], {"auto_remove": True}, False),
    (["-i"], {"stdin_open": True}, False),
    (["-t"], {"tty": True}, False),
    (["-it"], {"stdin_open": True, "tty": True}, False),
    (["--init"], {"init": True}, False),
    (["--rm", "-i", "--init"], {"auto_remove": True, "stdin_open": True, "init": True}, False),
    # 帶值 flag:inline 與雙 token 兩式等價
    (["--network=bridge"], {"network": "bridge"}, False),
    (["--network", "none"], {"network": "none"}, False),
    (["--memory", "512m"], {"mem_limit": "512m"}, False),
    (["--cpus", "1.5"], {"nano_cpus": 1_500_000_000}, False),
    # --pull always 走預拉,不進 kwargs
    (["--pull", "always"], {}, True),
    (["--pull", "missing"], {}, False),
    (["--rm", "--pull", "always"], {"auto_remove": True}, True),
])
def test_flags_to_kwargs(flags, expected_kwargs, expected_pull):
    kwargs, pull_always = _flags_to_kwargs(flags)
    assert kwargs == expected_kwargs
    assert pull_always is expected_pull
