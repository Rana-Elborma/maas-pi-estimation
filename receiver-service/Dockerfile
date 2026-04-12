# 1. Use a lightweight official Python image as the base image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the dependency file first
# This helps Docker cache the dependency installation step
COPY requirements.txt .

# 4. Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code into the container
COPY . .

# 6. Expose the port used by the FastAPI application
EXPOSE 8080

# 7. Define the command to run the receiver service
# 0.0.0.0 means the app listens on all container interfaces
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]