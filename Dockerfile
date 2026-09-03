# Multi-stage build: compile the frontend, then bake it into the backend
# image so one container serves both (same origin -- no CORS to configure
# in production, see backend/main.py's serve_spa).

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# No VITE_API_URL/VITE_API_KEY passed here on purpose -- the built bundle
# talks to whatever origin it's served from (see frontend/src/lib/api.js).
# The X-API-Key header itself is still required and is set via
# VITE_API_KEY at build time if you DO want it baked in; see DEPLOY.md.
ARG VITE_API_KEY=""
ENV VITE_API_KEY=${VITE_API_KEY}
RUN npm run build

# ---- Stage 2: backend + LibreOffice (needed to render each Excel sheet to
# an image for the GPT vision fill step) + poppler (pdf2image's pdftoppm) ----
FROM python:3.13-slim AS backend

# libreoffice-calc alone is frequently missing transitive deps for headless
# conversion in slim images; the full metapackage is the reliable option.
# fonts-dejavu-core keeps rendered PDFs from using garbled/missing-glyph
# fallback fonts. curl is only for the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    fonts-dejavu-core \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static

# uploads/ and the sqlite db both live under here -- mount your platform's
# persistent volume at /app/backend/uploads (see DEPLOY.md) and set
# DATABASE_URL=sqlite:///./uploads/preque.db so a single volume covers both.
RUN mkdir -p uploads/forms uploads/outputs uploads/project_files uploads/project_data_imports uploads/outputs

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
