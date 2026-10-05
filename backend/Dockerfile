FROM python:3.12-slim

# Install system dependencies for WeasyPrint, psycopg, and building extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-gobject0 \
    libjpeg-dev \
    libopenjp2-7-dev \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.2

# Set work directory
WORKDIR /app

# Configure poetry to install to global python inside container
RUN poetry config virtualenvs.create false

# Copy dependency files
COPY pyproject.toml /app/

# Generate lock file and install dependencies (including dev)
RUN poetry lock --no-update && poetry install --no-interaction --no-ansi

# Copy app code
COPY src/ /app/src/

# Expose port
EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "fira.main:app", "--host", "0.0.0.0", "--port", "8000"]
