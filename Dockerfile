FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-core fonts-noto-color-emoji ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask waitress requests anthropic google-genai pillow openpyxl xlrd pandas yt-dlp
RUN printf '#!/bin/sh\nexec /usr/bin/chromium --no-sandbox "$@"\n' > /usr/local/bin/chromium-run && chmod +x /usr/local/bin/chromium-run
WORKDIR /app
COPY . /app
CMD ["python", "cloudrun_main.py"]
