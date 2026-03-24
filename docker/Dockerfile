# ── Backend ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS backend

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/       ./src/
COPY skills/    ./skills/
COPY CLAUDE.md  ./CLAUDE.md
COPY scenarios/ ./scenarios/
COPY data/      ./data/

ENV PYTHONPATH=/app/src
ENV SKILLS_PATH=/app/skills
ENV CLAUDE_MD_PATH=/app/CLAUDE.md

EXPOSE 8002
CMD ["uvicorn", "demo_api:app", "--host", "0.0.0.0", "--port", "8002", \
     "--log-level", "info"]


# ── Frontend build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /ui
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ ./
ARG VITE_API_BASE=http://localhost:8002
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build


# ── Nginx serving both ────────────────────────────────────────────────────────
FROM nginx:alpine AS frontend
COPY --from=frontend-build /ui/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
