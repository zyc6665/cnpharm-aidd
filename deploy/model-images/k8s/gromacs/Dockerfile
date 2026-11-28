FROM condaforge/mambaforge:24.1.2-0 AS env_builder

# Build an offline-self-contained Python 3.11 + AmberTools + acpype + RDKit +
# MDAnalysis + ProLIF + MDTraj environment for protein-ligand complex MD.
# Keep prefix /opt/md-env identical in Stage 2 so conda script shebangs stay valid.
RUN mamba create -y -p /opt/md-env \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
        --override-channels \
        python=3.11 \
        ambertools \
        acpype \
        rdkit \
        "mdtraj==1.10.3" \
        "mdanalysis>=2.8" \
        "prolif>=2.1" \
        networkx \
        pandas \
        scipy \
        numpy \
        "minio==7.2.20" \
    && mamba clean -afy

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# GROMACS 2024.1 CUDA build（由 4090 现有 /data/gromacs 运行时裁剪而来）。
# 该构建链接 CUDA 10.1 的 libcufft.so.10，故把宿主同名库一并带入镜像，
# 避免依赖具体节点的 CUDA 小版本。
COPY bin /opt/gromacs/bin
COPY lib /opt/gromacs/lib
COPY top /opt/gromacs/share/gromacs/top
COPY cuda/libcufft.so.10 /usr/lib/x86_64-linux-gnu/libcufft.so.10
COPY cuda/libcufftw.so.10 /usr/lib/x86_64-linux-gnu/libcufftw.so.10

COPY --from=env_builder /opt/md-env /opt/md-env

# Provide /opt/conda and /opt/amber/anaconda3 layout aliases for resolve_amber_env().
RUN ln -sfn /opt/md-env /opt/conda \
    && mkdir -p /opt/amber/anaconda3/envs \
    && ln -sfn /opt/md-env /opt/amber/anaconda3/envs/AmberTools \
    && ln -sfn /opt/md-env/bin /opt/amber/anaconda3/bin \
    && ln -sfn /opt/md-env/lib /opt/amber/anaconda3/lib

ENV GMXDATA=/opt/gromacs/share/gromacs \
    AMBERHOME=/opt/md-env \
    LD_LIBRARY_PATH=/opt/gromacs/lib:/opt/md-env/lib \
    PATH=/opt/md-env/bin:/opt/gromacs/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY platform_adaptor /opt/aidd/platform_adaptor
COPY gromacs_platform.py /opt/aidd/gromacs/gromacs_platform.py
COPY mmpbsa_platform.py /opt/aidd/gromacs/mmpbsa_platform.py
COPY interactions_analysis.py /opt/aidd/gromacs/interactions_analysis.py
COPY trajectory_movie_pdb.py /opt/aidd/gromacs/trajectory_movie_pdb.py
COPY trajectory_movie.py /opt/aidd/gromacs/trajectory_movie.py
COPY ligand_parameterizer.py /opt/aidd/gromacs/ligand_parameterizer.py
RUN chmod +x /opt/aidd/platform_adaptor/*.sh /opt/aidd/gromacs/*.py

ENV PLATFORM_ADAPTOR_ROOT=/opt/aidd/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/aidd/gromacs/gromacs_platform.py \
    MODEL_PYTHON=/opt/md-env/bin/python \
    PLATFORM_PYTHON=/opt/md-env/bin/python

# 兼容存量 DB entrypoint（/opt/sciminer/...）：新镜像提供同名符号链接
RUN ln -sfn /opt/aidd /opt/sciminer

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/aidd/platform_adaptor/entrypoint.sh"]
