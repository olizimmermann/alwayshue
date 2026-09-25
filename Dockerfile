FROM python:3.11-slim

WORKDIR /app

COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Code only: secrets (.env) are injected at runtime via env_file, never baked into the image.
COPY app/*.py /app/
COPY app/static /app/static

RUN useradd -m appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data

USER appuser
ENV ALWAYSHUE_DATA=/app/data
VOLUME /app/data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
