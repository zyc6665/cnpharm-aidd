FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini python3 python3-pip libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# GROMACS 2024.1 CUDA build（由 4090 现有 /data/gromacs 运行时裁剪而来）。
# 该构建链接 CUDA 10.1 的 libcufft.so.10，故把宿主同名库一并带入镜像，
# 避免依赖具体节点的 CUDA 小版本。
COPY bin /opt/gromacs/bin
COPY lib /opt/gromacs/lib
COPY top /opt/gromacs/share/gromacs/top
COPY cuda/libcufft.so.10 /usr/lib/x86_64-linux-gnu/libcufft.so.10
COPY cuda/libcufftw.so.10 /usr/lib/x86_64-linux-gnu/libcufftw.so.10

ENV GMXDATA=/opt/gromacs/share/gromacs \
    LD_LIBRARY_PATH=/opt/gromacs/lib \
    PATH=/opt/gromacs/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple minio==7.2.10 mdtraj==1.10.3

COPY platform_adaptor /opt/sciminer/platform_adaptor
COPY gromacs_platform.py /opt/sciminer/gromacs/gromacs_platform.py
COPY mmpbsa_platform.py /opt/sciminer/gromacs/mmpbsa_platform.py
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/gromacs/*.py

ENV PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/gromacs/gromacs_platform.py \
    MODEL_PYTHON=/usr/bin/python3 \
    PLATFORM_PYTHON=/usr/bin/python3

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"]
