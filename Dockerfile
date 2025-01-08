FROM python:3.11-slim

# Install necessary packages and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    && pip install --no-cache-dir fastapi uvicorn requests \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only the necessary files
COPY app/main.py /app/
COPY app/hue.py /app/
COPY app/.env /app/

# Create a non-root user and give ownership of /app
RUN useradd -m appuser \
    && chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the application port
EXPOSE 8000

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


