# syntax=docker/dockerfile:1

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Warstwa zależności: przebudowuje się tylko po zmianie pyproject.toml.
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; open('/tmp/requirements.txt', 'w').write('\n'.join(p['dependencies']))" \
    && pip install -r /tmp/requirements.txt

COPY alembic.ini ./
COPY finbro ./finbro

RUN useradd --system --uid 10001 --no-create-home finbro
USER finbro

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Wewnątrz kontenera serwer słucha na 0.0.0.0; dostęp ogranicza publikacja portu na 127.0.0.1.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn finbro.web.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1"]
