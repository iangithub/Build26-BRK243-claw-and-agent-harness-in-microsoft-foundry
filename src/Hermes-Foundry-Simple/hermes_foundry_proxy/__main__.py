# ============================================================
# 【檔案說明】CLI 入口:python -m hermes_foundry_proxy
# 1. logging 全部導向 stderr,stdout 只留給 JSON-RPC response
# 2. stdin/stdout 改用 UTF-8(Windows 主控台預設編碼可能不是 UTF-8)
# 3. 啟動後持續從 stdin 讀取請求直到 EOF;Ctrl+C 優雅退出
# ============================================================

from __future__ import annotations

import logging
import sys

from .config import ENDPOINT_ENV, Settings
from .foundry import FoundryClient
from .proxy import run

log = logging.getLogger("hermes_foundry_proxy")


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    settings = Settings.from_env()
    if not settings.invocations_endpoint:
        # 不在啟動階段 crash;prompt.submit 時才回 JSON-RPC error
        log.warning("%s is not set; prompt.submit will fail until it is.", ENDPOINT_ENV)
    client = FoundryClient(settings)
    log.info("hermes-foundry-simple proxy ready; reading JSON-RPC from stdin")
    try:
        return run(sys.stdin, sys.stdout, client)
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
