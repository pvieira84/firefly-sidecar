FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BIND=0.0.0.0 PORT=8080 DATA_DIR=/data
RUN groupadd --gid 10001 sidecar && useradd --uid 10001 --gid sidecar --no-create-home sidecar && mkdir /data && chown sidecar:sidecar /data
WORKDIR /app
COPY --chown=sidecar:sidecar sidecar /app/sidecar
USER sidecar
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)"
CMD ["python", "-m", "sidecar.server"]
