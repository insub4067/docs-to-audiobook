import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import mimetypes
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from state import STATIC_DIR

app = FastAPI(title="Docs to Audiobook Converter - Hybrid")

# 프론트엔드는 같은 출처에서 상대 경로로만 API를 호출하므로 와일드카드가
# 필요 없다. allow_origins=["*"] 와 allow_credentials=True 조합은 잘못된
# 설정이기도 하다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://docs-to-audiobook.onrender.com",
        "https://docs-to-audiobook.fly.dev",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

from routes import extract_url as extract_url_routes
from routes import extract_youtube as extract_youtube_routes
from routes import import_drive as import_drive_routes
from routes import scan_text as scan_text_routes
from routes import upload as upload_routes
from routes import paste_text as paste_text_routes
from routes import tts as tts_routes
from routes import default_book as default_book_routes
from routes import share as share_routes
from routes import audiobooks as audiobooks_routes
from routes import folders as folders_routes
from routes import auth_social as auth_social_routes
from routes import system as system_routes
from routes import notifications as notifications_routes
from routes import news as news_routes
app.include_router(extract_url_routes.router)
app.include_router(extract_youtube_routes.router)
app.include_router(import_drive_routes.router)
app.include_router(scan_text_routes.router)
app.include_router(upload_routes.router)
app.include_router(paste_text_routes.router)
app.include_router(tts_routes.router)
app.include_router(default_book_routes.router)
app.include_router(share_routes.router)
app.include_router(audiobooks_routes.router)
app.include_router(folders_routes.router)
app.include_router(auth_social_routes.router)
app.include_router(system_routes.router)
app.include_router(notifications_routes.router)
app.include_router(news_routes.router)

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup_event():
    from auth import get_secret_key
    from cleanup import cleanup_expired_files_loop

    get_secret_key()
    asyncio.create_task(cleanup_expired_files_loop())
    asyncio.create_task(tts_routes.resume_background_synthesis_jobs())
    # 부팅 시에는 클라우드에 있으면 내려받기만 하고 합성은 하지 않는다.
    # 여기서 합성을 시작하면 공유 CPU 1개를 점유해 사용자 변환이 막힌다.
    # 클라우드에 없으면 상태를 pending으로 두고, 실제로 요청이 올 때
    # /api/default-book이 한 번만 생성한다(락으로 중복 방지).
    asyncio.create_task(default_book_routes.prepare_default_book_from_cache())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
