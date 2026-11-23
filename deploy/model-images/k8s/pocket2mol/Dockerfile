FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
COPY env.tar.gz /tmp/env.tar.gz
RUN mkdir -p /opt/conda && tar -xzf /tmp/env.tar.gz -C /opt/conda && rm /tmp/env.tar.gz && PATH=/opt/conda/bin:$PATH /opt/conda/bin/conda-unpack
RUN PATH=/opt/conda/bin:$PATH /opt/conda/bin/pip install --no-cache-dir -i https://pypi.org/simple minio==7.2.10
ENV PATH=/opt/conda/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/aidd/Pocket2Mol-main PLATFORM_ADAPTOR_ROOT=/opt/aidd/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/aidd/Pocket2Mol-main/platform_run.sh \
    MODEL_PYTHON=/opt/conda/bin/python CONDA_EXE=/opt/conda/bin/conda \
    PLATFORM_POSTPROCESS_MODEL=pocket2mol PLATFORM_LEGACY_REQUEST_BRIDGE=1
COPY platform_adaptor /opt/aidd/platform_adaptor
ADD model.tar.gz /opt/aidd/
RUN chmod +x /opt/aidd/platform_adaptor/*.sh /opt/aidd/Pocket2Mol-main/platform_run.sh
# 兼容存量 DB entrypoint（/opt/sciminer/...）：新镜像提供同名符号链接
RUN ln -sfn /opt/aidd /opt/sciminer

ENTRYPOINT ["/usr/bin/tini","--","/opt/aidd/platform_adaptor/entrypoint.sh"]
