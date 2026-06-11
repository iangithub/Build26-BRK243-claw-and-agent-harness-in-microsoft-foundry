# ============================================================
# 【檔案說明】CLI 入口:python -m foundry_hermes_qa_agent
# 1. logging 全部導向 stderr,不污染 protocol response
# 2. --port 參數直接傳給 AgentServer 的 run();未指定時
#    套件自己的解析順序是 PORT 環境變數 → 預設 8088
# 3. 啟動時檢查 AZURE_OPENAI_* 設定並提示(僅警告,不中止——
#    缺設定時呼叫端會收到清楚的 500 錯誤)
# ============================================================

from __future__ import annotations

import argparse
import logging
import sys

from .app import create_app
from .errors import MissingConfigError
from .settings import Settings

log = logging.getLogger("foundry_hermes_qa_agent")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m foundry_hermes_qa_agent",
        description=(
            "Microsoft Foundry Hosted Agent(Invocations Protocol):"
            "接收 hermes.rpc prompt.submit payload,呼叫 Azure OpenAI 回答,"
            "回傳 {\"type\": \"message.complete\", \"text\": ...}。"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="監聽 port(預設讀 PORT 環境變數,否則用 AgentServer 套件預設 8088)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        Settings.from_env()
    except MissingConfigError as exc:
        log.warning("%s — prompt.submit calls will fail until these are set.", exc)

    app = create_app()
    log.info("foundry-hermes-qa-agent starting (Invocations Protocol)")
    app.run(port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
