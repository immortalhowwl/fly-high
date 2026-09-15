FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 FLYHIGH_ALLOWED_HOSTS=flyhigh.fun
COPY flyhigh/ ./flyhigh/
COPY web/ ./web/
RUN python -c "from pathlib import Path; import shutil; out=open('web/fly-hero.mp4','wb'); [shutil.copyfileobj(p.open('rb'),out) for p in sorted(Path('web/film-source').glob('part-*'))]; out.close()"
COPY examples/copy.report.json ./examples/copy.report.json
COPY --chown=65534:65534 data/research.snapshot.json ./data/research.snapshot.json
COPY --chown=65534:65534 data/wallet-seeded.report.json ./data/wallet-seeded.report.json
COPY --chown=65534:65534 data/market-history/copy.latest.json ./data/market-history/copy.latest.json
COPY --chown=65534:65534 data/hypothesis-replay.report.json ./data/hypothesis-replay.report.json
RUN chown -R 65534:65534 /app/data
USER 65534:65534
EXPOSE 8080
CMD ["python", "-m", "flyhigh.server", "--public"]
