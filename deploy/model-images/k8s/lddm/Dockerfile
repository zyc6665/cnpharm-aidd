FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 基镜像已自带 Python 3.11 + PyTorch 2.6.0 + CUDA 12.4；保留 torch 本体不动，
# 锁住 numpy==1.26.4 以匹配 rdkit==2023.9.6，并补齐 torch-scatter / LDDM 推理依赖。
RUN pip install --no-cache-dir --no-deps \
        -f https://data.pyg.org/whl/torch-2.6.0+cu124.html \
        torch-scatter==2.1.2+pt26cu124 \
    && pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        "numpy==1.26.4" \
        "rdkit==2023.9.6" \
        "biopython==1.83" \
        "scipy==1.13.0" \
        "pandas==2.2.3" \
        "pot==0.9.4" \
        "einops>=0.8.0" \
        "tqdm" \
        "setuptools" \
        "lightning>=2.3.3" \
        "torch-geometric==2.7.0" \
        "prody>=2.4.1" \
        "prolif==2.0.3" \
        "posebusters==0.3.1" \
        "useful-rdkit-utils==0.65" \
        "fcd==1.2.2" \
        "biotite>=1.5.0" \
        "minio==7.2.10"

# 构建上下文中需包含：
#   - repo/（LPDI-EPFL/lddm 源码，含 checkpoints/lddm.ckpt）
#   - platform_adaptor/（来自 deploy/kubernetes/model-image-template/platform_adaptor）
#   - lddm_platform.py 与 platform_run.sh
COPY repo /opt/aidd/lddm
COPY platform_adaptor /opt/aidd/platform_adaptor
COPY lddm_platform.py /opt/aidd/lddm/lddm_platform.py
COPY platform_run.sh /opt/aidd/lddm/platform_run.sh

RUN chmod +x /opt/aidd/platform_adaptor/*.sh /opt/aidd/lddm/platform_run.sh /opt/aidd/lddm/lddm_platform.py \
    && ln -sfn /opt/aidd /opt/sciminer

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/aidd/lddm \
    PLATFORM_ADAPTOR_ROOT=/opt/aidd/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/aidd/lddm/platform_run.sh \
    MODEL_PYTHON=/opt/conda/bin/python \
    PLATFORM_PYTHON=/opt/conda/bin/python \
    LDDM_CHECKPOINT=/opt/aidd/lddm/checkpoints/lddm.ckpt \
    PLATFORM_POSTPROCESS_MODEL=lddm \
    PLATFORM_LEGACY_REQUEST_BRIDGE=1

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/aidd/platform_adaptor/entrypoint.sh"]
