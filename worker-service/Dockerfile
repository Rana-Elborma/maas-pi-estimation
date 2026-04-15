# 1. Lightweight official Python image
FROM python:3.11-slim

# 2. Working directory inside the container
WORKDIR /app

# 3. Copy and install dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the application code
COPY . .

# 5. Expose the port used by the FastAPI application
EXPOSE 8080

# 6. Start the worker service
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
