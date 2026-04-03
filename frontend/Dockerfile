FROM python:3.11-slim

LABEL maintainer="InfoSec DE/AT" \
      description="Harmonizer Enterprise SPA Frontend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY server.py /app/server.py
COPY static/ /app/static/

EXPOSE 3001

# Health check — verify the frontend serves index.html
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3001/')" || exit 1

CMD ["python", "server.py"]
