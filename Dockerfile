FROM python:3.12-slim

WORKDIR /app

ENV MPLBACKEND=Agg
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# Install Python deps (everything in one layer)
COPY web/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source (pipeline code)
COPY src/ ./src/

# Copy web backend
COPY web/backend/ ./web/backend/

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
