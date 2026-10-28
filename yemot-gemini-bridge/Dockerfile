FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd -r -u 10001 bridge
COPY bridge ./bridge
USER bridge
# SIP_PORT defaults to 5060; the probe sends a SIP OPTIONS to our own socket
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -m bridge.probe 127.0.0.1 --port ${SIP_PORT:-5060} || exit 1
CMD ["python", "-m", "bridge.main"]
