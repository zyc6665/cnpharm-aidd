ARG BASE_IMAGE=python:3.10-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/aidd/model \
    PLATFORM_ADAPTOR_ROOT=/opt/aidd/platform_adaptor

WORKDIR /opt/aidd

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY model /opt/aidd/model
COPY platform_adaptor /opt/aidd/platform_adaptor

RUN if [ -f /opt/aidd/model/requirements.txt ]; then \
        python -m pip install --no-cache-dir -r /opt/aidd/model/requirements.txt; \
    fi \
    && python -m pip install --no-cache-dir -r /opt/aidd/platform_adaptor/requirements.txt \
    && chmod +x /opt/aidd/model/platform_run.sh \
    && chmod +x /opt/aidd/platform_adaptor/*.sh

# 兼容存量 DB entrypoint（/opt/sciminer/...）：新镜像提供同名符号链接
RUN ln -sfn /opt/aidd /opt/sciminer

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/aidd/platform_adaptor/entrypoint.sh"]
