# Sylva on Hugging Face Spaces (Docker SDK). Built by scripts/deploy_hf_space.py, which
# stages this file at the root of the Space repository together with the code and demo data.

# ---- frontend build ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

# ---- runtime ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    SYLVA_DATA_DIR=/app/data \
    SYLVA_FRONTEND_DIST=/app/frontend/dist \
    SYLVA_DEVICE=cpu
RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r backend/requirements.txt
COPY --chown=user backend/ backend/
COPY --chown=user configs/ configs/
COPY --chown=user docs/ docs/
COPY --chown=user models/ models/
COPY --chown=user demo_data/ data/
COPY --chown=user deploy/huggingface/start.sh start.sh
COPY --from=web --chown=user /web/dist frontend/dist
USER user
EXPOSE 7860
CMD ["bash", "start.sh"]
