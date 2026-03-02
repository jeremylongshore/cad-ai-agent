FROM python:3.12-slim

WORKDIR /app

ENV MPLBACKEND=Agg
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# System deps for pymupdf fallback + matplotlib font rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install ODA File Converter for DWG support
RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && wget -q "https://download.opendesign.com/guestfiles/ODAFileConverter/ODAFileConverter_QT6_lnxX64_8.3dll_25.12.deb" \
       -O /tmp/oda.deb \
    && echo "15facc7301b905a1b1aa742f7eeb936f96a1ad3f1828e8db7a444f4b572c7395  /tmp/oda.deb" | sha256sum -c - \
    && (dpkg -i /tmp/oda.deb || apt-get install -f -y) \
    && rm /tmp/oda.deb \
    && apt-get purge -y wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (everything in one layer)
COPY web/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source (pipeline code)
COPY src/ ./src/

# Copy web backend
COPY web/backend/ ./web/backend/

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
