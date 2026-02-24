FROM python:3.12-slim

WORKDIR /app

# System deps for matplotlib rendering (headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV MPLBACKEND=Agg

# Install Python deps
COPY web/backend/requirements.txt ./web-requirements.txt
RUN pip install --no-cache-dir -r web-requirements.txt

# Copy project source (pipeline code)
COPY src/ ./src/
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[draw,convert,gemini]"

# Copy web backend
COPY web/backend/ ./web/backend/

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
