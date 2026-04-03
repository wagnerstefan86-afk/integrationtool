FROM python:3.11-slim

LABEL maintainer="InfoSec DE/AT" \
      description="Harmonizer Report Viewer (minimal)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Simple static file server for viewing Markdown reports
# Uses Python's built-in http.server with a minimal wrapper
COPY server.py /app/server.py

EXPOSE 3001

CMD ["python", "server.py"]
