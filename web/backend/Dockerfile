# ─── Base image ───────────────────────────────────────────────────────
# Python 3.12 slim: small footprint, no dev headers.
FROM python:3.12-slim

WORKDIR /app

# ─── Environment variables ────────────────────────────────────────────
# MPLBACKEND=Agg: headless matplotlib (no display server needed).
# PYTHONDONTWRITEBYTECODE: skip .pyc files in container.
# PYTHONPATH: let imports find the pipeline source under src/.
ENV MPLBACKEND=Agg
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# ─── System dependencies ─────────────────────────────────────────────
# libglib2.0-0: required by pymupdf (PDF → DXF fallback converter).
# libfontconfig1: font rendering for matplotlib previews.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# ─── ODA File Converter (optional — DWG support) ─────────────────────
# ODA enables DWG → DXF conversion.  DXF and PDF uploads work without it.
# The backend returns HTTP 422 if a user uploads a DWG and ODA is missing.
#
# Guard: ODA's download URL sometimes redirects to an HTML page (~6KB)
# instead of the real .deb (~60MB).  We check the file size (>1MB) before
# attempting to install.  If the download is bad, we skip with a warning
# and the build continues without DWG support.
RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && wget -q "https://download.opendesign.com/guestfiles/ODAFileConverter/ODAFileConverter_QT6_lnxX64_8.3dll_25.12.deb" \
       -O /tmp/oda.deb \
    && ODA_SIZE=$(stat -c%s /tmp/oda.deb 2>/dev/null || echo 0) \
    && if [ "$ODA_SIZE" -gt 1000000 ]; then \
         echo "ODA package looks valid (${ODA_SIZE} bytes) — installing..." \
         && (dpkg -i /tmp/oda.deb || apt-get install -f -y) \
         && echo "ODA File Converter installed successfully"; \
       else \
         echo "WARNING: ODA download is only ${ODA_SIZE} bytes (expected ~60MB)." \
         && echo "Skipping ODA install — DWG uploads will return HTTP 422."; \
       fi \
    && rm -f /tmp/oda.deb \
    && apt-get purge -y wget \
    && rm -rf /var/lib/apt/lists/* \
    || true

# ─── Python dependencies ─────────────────────────────────────────────
# Single pip install layer for cacheability.
COPY web/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ─── Application source ──────────────────────────────────────────────
# Pipeline modules (models, core, llm, settings, etc.)
COPY src/ ./src/

# FastAPI web backend (routes, middleware, auth)
COPY web/backend/ ./web/backend/

# ─── Runtime ──────────────────────────────────────────────────────────
ENV PORT=8080
EXPOSE 8080

# Uvicorn with info-level logging.  Cloud Run injects $PORT at runtime.
CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
