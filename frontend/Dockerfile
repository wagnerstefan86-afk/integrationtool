FROM python:3.11-slim

LABEL maintainer="InfoSec DE/AT" \
      description="Harmonizer Enterprise SPA Frontend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY server.py /app/server.py
COPY static/ /app/static/

EXPOSE 3001

CMD ["python", "server.py"]
