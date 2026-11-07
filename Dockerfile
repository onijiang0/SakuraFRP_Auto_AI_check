FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

WORKDIR /app
COPY requirements.container.txt ./
RUN pip install --no-cache-dir -r requirements.container.txt \
    && mkdir -p /data \
    && chown pwuser:pwuser /data \
    && chmod 700 /data
COPY main.py ai_service.py logger.py sidecar.py ./
ENV SAKURAFRP_DATA_DIR=/data PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PYTHONUNBUFFERED=1
USER pwuser
EXPOSE 8765
CMD ["python", "-u", "sidecar.py"]
