# A small, standard image for a Python web app.
FROM python:3.12-slim

# Don't write .pyc files; print logs straight away (no buffering).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first: Docker caches this layer until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then copy the code.
COPY agent.py server.py ./
COPY static ./static

# Run as a normal user, not root, and keep chat data in /data (a volume).
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
ENV DATA_DIR=/data HOST=0.0.0.0 PORT=8000

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["python", "server.py"]
