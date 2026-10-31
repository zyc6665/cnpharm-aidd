FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# AutoDock Vina 1.2.7 + Meeko（受体/配体 PDBQT 制备）+ RDKit（SDF 读写、构象）
RUN pip install --no-cache-dir -i https://pypi.org/simple \
        vina==1.2.7 meeko==0.6.1 rdkit==2024.9.6 numpy==1.26.4 minio==7.2.10

COPY platform_adaptor /opt/sciminer/platform_adaptor
COPY vina_platform.py /opt/sciminer/vina/vina_platform.py
RUN chmod +x /opt/sciminer/platform_adaptor/*.sh /opt/sciminer/vina/vina_platform.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    DRP_MODEL_ENTRY=/opt/sciminer/vina/vina_platform.py \
    MODEL_PYTHON=/usr/local/bin/python \
    PLATFORM_PYTHON=/usr/local/bin/python

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"]
