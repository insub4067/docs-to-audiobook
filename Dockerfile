# ---- 프론트엔드 빌드 스테이지 (Vue + Vite + TS) ----
# 서버는 항상 켜져 있어야 해서(콜드 스타트 방지, fly.toml 참고) 컨테이너
# 시작 시점에 빌드하면 안 된다. 이미지 빌드 시점에 끝내고, 최종 이미지에는
# Node.js가 남지 않는다.
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && npm run build:app

# Use official light-weight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /code

# Copy requirements file first for caching
COPY backend/requirements.txt /code/requirements.txt

# Install dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Set up user 1000 for Hugging Face Space security requirements
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set working directory inside user home/app
WORKDIR $HOME/app

# Copy application files (preserving structure)
COPY --chown=user:user . $HOME/app

# 프론트엔드 빌드 스테이지의 결과물을 가져온다(vite.config.ts/
# vite.app.config.ts의 outDir 기준, frontend-build 스테이지의 WORKDIR이
# /frontend라 실제 경로는 /frontend/static/dist/{admin,app})
COPY --from=frontend-build --chown=user:user /frontend/static/dist/admin $HOME/app/frontend/static/dist/admin
COPY --from=frontend-build --chown=user:user /frontend/static/dist/app $HOME/app/frontend/static/dist/app

# Ensure uploads directory is present and writable
RUN mkdir -p $HOME/app/backend/uploads && chmod -R 777 $HOME/app/backend/uploads

# Expose Hugging Face Space default port
EXPOSE 7860

# Run FastAPI app with Uvicorn on port 7860. main.py는 backend/ 아래로
# 옮겨졌고 내부 import(from routes import tts 등)는 그대로라, --app-dir로
# backend/를 파이썬 모듈 검색 루트로 잡아준다(코드 변경 없이 해결).
CMD ["uvicorn", "main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
