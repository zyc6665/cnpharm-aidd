# MolP-PC 计算镜像（GPU 版）
#
# 构建前必须确认 env.tar.gz 里的 torch 是 **CUDA 轮子**。
#
# 1.0.0 的教训：env 里是 `torch==2.0.1+cpu`，Pod 申请了 `nvidia.com/gpu` 却
# `torch.cuda.is_available()` 恒为 False，模型静默退回 CPU 跑（单任务 47s，GPU 版 23s），
# 日志里一句报错都没有。因此 1.1.0 的 env 必须先在宿主环境装好 GPU 三件套再 conda-pack：
#
#   pip install --force-reinstall --no-deps torch==2.0.1+cu118 torchvision==0.15.2+cu118 \
#       torchaudio==2.0.2+cu118 -i https://download.pytorch.org/whl/cu118
#   pip install --force-reinstall --no-deps torch-scatter==2.1.2+pt20cu118 \
#       -f https://data.pyg.org/whl/torch-2.0.1+cu118.html
#   pip install --force-reinstall --no-deps dgl==1.1.2+cu118 \
#       -f https://data.dgl.ai/wheels/cu118/repo.html
#
# 打包前在宿主上验一次：`python -c "import torch,dgl;assert torch.cuda.is_available()"`。
# 若 conda-pack 报 caffe2 文件缺失（torch 2.0 已移除 caffe2，但旧 conda-meta 记录还在），
# 删掉 `conda-meta/pytorch-*.json` 这类过期记录，再用 ignore_missing_files=True 打包。
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
COPY env.tar.gz /tmp/env.tar.gz
RUN mkdir -p /opt/conda && tar -xzf /tmp/env.tar.gz -C /opt/conda && rm /tmp/env.tar.gz && PATH=/opt/conda/bin:$PATH /opt/conda/bin/conda-unpack
RUN PATH=/opt/conda/bin:$PATH /opt/conda/bin/pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple minio==7.2.10
ENV PATH=/opt/conda/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/sciminer/MolP-PC PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/MolP-PC/platform_run.sh \
    MOLP_PC_PYTHON=/opt/conda/bin/python CONDA_EXE=/opt/conda/bin/conda \
    PLATFORM_POSTPROCESS_MODEL=molp-pc PLATFORM_LEGACY_REQUEST_BRIDGE=1 \
    LD_LIBRARY_PATH=/opt/conda/lib:/opt/conda/lib/python3.8/site-packages/nvidia/cublas/lib:/opt/conda/lib/python3.8/site-packages/nvidia/cusparse/lib:/opt/conda/lib/python3.8/site-packages/nvidia/cusolver/lib
COPY platform_adaptor /opt/sciminer/platform_adaptor
ADD model.tar.gz /opt/sciminer/
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/MolP-PC/platform_run.sh
ENTRYPOINT ["/usr/bin/tini","--","/opt/sciminer/platform_adaptor/entrypoint.sh"]
