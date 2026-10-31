FROM 127.0.0.1:30500/aidd/compute-boltz2:1.0.0

# Reuse the CUDA/py3.11 base (torch 2.6 + minio). Add TheraPainter's research deps.
RUN /opt/conda/bin/pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    transformers==4.46.3 \
    tokenizers==0.20.3 \
    scikit-learn==1.5.2 \
    biopython \
    accelerate \
    sentencepiece \
    modlamp \
    python-Levenshtein \
    ankh \
    fair-esm

# Platform adaptor: legacy request bridge + DualPep result postprocess.
COPY request_to_legacy.py /opt/sciminer/platform_adaptor/request_to_legacy.py
COPY postprocess_result.py /opt/sciminer/platform_adaptor/postprocess_result.py

ENV DRP_MODEL_ENTRY=/opt/TheraPainter/platform_run.sh \
    MODEL_PYTHON=/opt/conda/bin/python \
    THERAPAINTER_MODEL_ROOT=/opt/TheraPainter \
    PLATFORM_LEGACY_REQUEST_BRIDGE=1 \
    PLATFORM_POSTPROCESS_MODEL=therapainter
