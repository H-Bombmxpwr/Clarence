# Clarence bot. Audio is handled by the separate Lavalink service (see lavalink/),
# so no FFmpeg/Opus is needed here.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Persistent data (mount a volume here and set DATA_DIR=/data)
ENV DATA_DIR=/data
CMD ["python", "main.py"]
