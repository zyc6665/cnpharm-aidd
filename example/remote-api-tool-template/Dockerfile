FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY "requirements.txt" "/app/requirements.txt"
RUN pip install --no-cache-dir -r "/app/requirements.txt"

COPY "app" "/app/app"
COPY "export_platform_tool.py" "/app/export_platform_tool.py"
COPY "platform_tool.json" "/app/platform_tool.json"
COPY "smoke_test_payload.json" "/app/smoke_test_payload.json"

RUN mkdir -p "/app/model" "/tmp/remote-api-tool-template"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
