ARG BASE_IMAGE=python:3.10-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/sciminer/model \
    PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor

WORKDIR /opt/sciminer

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY model /opt/sciminer/model
COPY platform_adaptor /opt/sciminer/platform_adaptor

RUN if [ -f /opt/sciminer/model/requirements.txt ]; then \
        python -m pip install --no-cache-dir -r /opt/sciminer/model/requirements.txt; \
    fi \
    && python -m pip install --no-cache-dir -r /opt/sciminer/platform_adaptor/requirements.txt \
    && chmod +x /opt/sciminer/model/platform_run.sh \
    && chmod +x /opt/sciminer/platform_adaptor/*.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"]
