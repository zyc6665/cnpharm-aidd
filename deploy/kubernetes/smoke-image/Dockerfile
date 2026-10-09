FROM alpine:3.20

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages minio==7.2.3

COPY run-smoke.py /usr/local/bin/run-smoke.py
COPY run-smoke.sh /usr/local/bin/run-smoke.sh
RUN chmod 0755 /usr/local/bin/run-smoke.py /usr/local/bin/run-smoke.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/run-smoke.sh"]
