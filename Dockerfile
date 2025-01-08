FROM python:3.11-slim

# Install necessary packages
RUN apt-get update && apt-get install -y \
    && pip install --no-cache-dir fastapi uvicorn requests \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# Set working directory
WORKDIR /app

# Copy application code
COPY app /app

# Expose the port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
