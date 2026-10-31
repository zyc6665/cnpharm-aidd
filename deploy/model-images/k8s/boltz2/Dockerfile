FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

# Boltz-2 2.2.1（基镜像自带 torch 2.6 + CUDA 12.4）。先降 numpy 到 <2，
# 否则 boltz 的 numpy<2 约束与基镜像的 numpy 2.x 直接冲突。
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "numpy<2" \
    && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple boltz==2.2.1 minio==7.2.10

COPY platform_adaptor /opt/sciminer/platform_adaptor
COPY boltz_platform.py /opt/sciminer/boltz2/boltz_platform.py
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/boltz2/boltz_platform.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/boltz2/boltz_platform.py \
    MODEL_PYTHON=/opt/conda/bin/python \
    PLATFORM_PYTHON=/opt/conda/bin/python \
    PLATFORM_LEGACY_REQUEST_BRIDGE=1 \
    BOLTZ_CACHE=/opt/boltz2_cache

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"]
