FROM python:3.9

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Adjust file permissions (while still root)
RUN chmod +x /app/entrypoint.sh

RUN mkdir /app/media

# Expose the application port
ENTRYPOINT ["/app/entrypoint.sh"]
EXPOSE 8000

# Start Gunicorn server
CMD ["gunicorn", "--workers=3", "--bind=0.0.0.0:8000", "--config", "gunicorn-cfg.py", "core.wsgi"]