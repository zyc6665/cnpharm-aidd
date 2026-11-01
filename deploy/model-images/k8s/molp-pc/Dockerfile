FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
COPY env.tar.gz /tmp/env.tar.gz
RUN mkdir -p /opt/conda && tar -xzf /tmp/env.tar.gz -C /opt/conda && rm /tmp/env.tar.gz && PATH=/opt/conda/bin:$PATH /opt/conda/bin/conda-unpack
RUN PATH=/opt/conda/bin:$PATH /opt/conda/bin/pip install --no-cache-dir -i https://pypi.org/simple minio==7.2.10
ENV PATH=/opt/conda/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PACKAGE_ROOT=/opt/sciminer/MolP-PC PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/MolP-PC/platform_run.sh \
    MOLP_PC_PYTHON=/opt/conda/bin/python CONDA_EXE=/opt/conda/bin/conda \
    PLATFORM_POSTPROCESS_MODEL=molp-pc PLATFORM_LEGACY_REQUEST_BRIDGE=1
COPY platform_adaptor /opt/sciminer/platform_adaptor
ADD model.tar.gz /opt/sciminer/
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/MolP-PC/platform_run.sh
ENTRYPOINT ["/usr/bin/tini","--","/opt/sciminer/platform_adaptor/entrypoint.sh"]
