FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
COPY env.tar.gz /tmp/env.tar.gz
RUN mkdir -p /opt/conda && tar -xzf /tmp/env.tar.gz -C /opt/conda && rm /tmp/env.tar.gz && PATH=/opt/conda/bin:$PATH /opt/conda/bin/conda-unpack
# minio 走对象存储适配层；numpy 固定 1.26.4 避免 minio 依赖升级到 numpy 2.x 与 conda 环境冲突
RUN PATH=/opt/conda/bin:$PATH /opt/conda/bin/pip install --no-cache-dir -i https://pypi.org/simple minio==7.2.10 "numpy==1.26.4"
ENV PATH=/opt/conda/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/sciminer/MSIGN PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/MSIGN/platform_run.sh \
    MODEL_PYTHON=/opt/conda/bin/python CONDA_EXE=/opt/conda/bin/conda \
    PLATFORM_POSTPROCESS_MODEL=msign PLATFORM_LEGACY_REQUEST_BRIDGE=1
COPY platform_adaptor /opt/sciminer/platform_adaptor
# model_v2.tar.gz 由 prepare_build_context.sh 生成（内含带 --center-from-protein 的 platform_run.sh）
ADD model_v2.tar.gz /opt/sciminer/
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/MSIGN/platform_run.sh
ENTRYPOINT ["/usr/bin/tini","--","/opt/sciminer/platform_adaptor/entrypoint.sh"]
