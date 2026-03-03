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
ENV QT_QPA_PLATFORM=offscreen

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
# The .deb is self-hosted in GCS (ODA's download page requires SSO).
# CI downloads it with authenticated gcloud before `docker build`, placing
# it at ./oda.deb in the build context.  xvfb provides a virtual display
# for ODA's Qt6 GUI (ezdxf spawns Xvfb automatically).
#
# Guard: if oda.deb is missing or tiny (<1MB), we skip with a warning.
COPY oda.deb* /tmp/
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb libstdc++6 libxkbcommon0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 \
    && ODA_SIZE=$(stat -c%s /tmp/oda.deb 2>/dev/null || echo 0) \
    && if [ "$ODA_SIZE" -gt 1000000 ]; then \
         echo "ODA package looks valid (${ODA_SIZE} bytes) — installing..." \
         && (dpkg -i /tmp/oda.deb || apt-get install -f -y) \
         && echo "ODA File Converter installed successfully"; \
       else \
         echo "WARNING: oda.deb missing or only ${ODA_SIZE} bytes (expected ~60MB)." \
         && echo "Skipping ODA install — DWG uploads will return HTTP 422."; \
       fi \
    && rm -f /tmp/oda.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

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
