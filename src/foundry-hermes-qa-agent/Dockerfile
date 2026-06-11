# 官方 python slim image;container 內不含任何 secret——
# 認證走 Hosted Agent 的 managed identity(DefaultAzureCredential),
# 設定全部由環境變數注入(見 agent.yaml)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
USER appuser

# AgentServer 預設監聽 8088,可用 PORT 環境變數覆寫
EXPOSE 8088

CMD ["python", "-m", "foundry_hermes_qa_agent"]
