FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 FLYHIGH_ALLOWED_HOSTS=flyhigh.fun
COPY flyhigh/ ./flyhigh/
COPY web/ ./web/
COPY examples/copy.report.json ./examples/copy.report.json
COPY --chown=65534:65534 data/research.snapshot.json ./data/research.snapshot.json
RUN chown 65534:65534 /app/data
USER 65534:65534
EXPOSE 8080
CMD ["python", "-m", "flyhigh.server", "--public"]
