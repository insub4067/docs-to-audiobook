"""기본 제공 오디오북(데미안): 서버 기동 시 미리 생성해 캐시."""
import os
import json
import asyncio
import hashlib
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from state import BASE_DIR, STATIC_DIR, AUDIOBOOK_BUCKET
from text_processing import extract_text
from routes import tts as tts_routes
from tts_providers import get_tts_provider
from tts_providers.voice_catalog import DEFAULT_VOICE_KEY

router = APIRouter()

DEFAULT_BOOK_DIR = os.path.join(BASE_DIR, "default_book")
DEFAULT_BOOK_SOURCE = os.path.join(STATIC_DIR, "samples", "demian.txt")
DEFAULT_BOOK_TITLE = "데미안"
DEFAULT_BOOK_VOICE = DEFAULT_VOICE_KEY

default_book_state = {"status": "pending", "error": None}
default_book_lock = asyncio.Lock()


def _default_book_fingerprint() -> str:
    """공급자 + 음성 + 원문 내용으로 캐시 키를 만든다.

    음성만 넣었을 때는 원문을 바꿔도 키가 그대로라, 예전 내용으로 만든
    오디오가 계속 재사용됐다(축약본 3챕터가 전문으로 바꾼 뒤에도 남았다).
    내용 해시를 함께 넣어 원문이 바뀌면 자동으로 다시 만들게 한다.

    공급자(TTS_PROVIDER)도 포함한다 — voice_key는 그대로 두고 공급자만
    edge_tts <-> google로 바꿔도 실제 오디오가 완전히 달라지는데, 공급자가
    빠져 있으면 이미 만들어둔 예전 공급자 캐시를 계속 재사용해버린다."""
    h = hashlib.sha256()
    h.update(DEFAULT_BOOK_VOICE.encode())
    h.update(get_tts_provider().name.encode())
    try:
        with open(DEFAULT_BOOK_SOURCE, "rb") as f:
            h.update(f.read())
    except OSError:
        pass
    return f"{DEFAULT_BOOK_VOICE}.{h.hexdigest()[:10]}"


def default_book_paths():
    fp = _default_book_fingerprint()
    return (
        os.path.join(DEFAULT_BOOK_DIR, f"audio.{fp}.mp3"),
        os.path.join(DEFAULT_BOOK_DIR, f"meta.{fp}.json"),
    )


# 기본 제공 오디오북을 클라우드에 한 번만 만들어 두는 자리.
# 디스크는 재배포마다 날아가므로 여기 없으면 부팅할 때마다 36,000자를
# 다시 합성하게 되고, 공유 CPU 1개를 점유해 사용자 변환까지 굶긴다.
# 로컬과 같은 키(음성 + 원문 해시)를 클라우드에도 쓴다


def default_book_remote_keys():
    fp = _default_book_fingerprint()
    return (
        f"_default/demian.{fp}.mp3",
        f"_default/demian.{fp}.meta.json",
    )


def _restore_default_book_from_cloud(audio_path: str, meta_path: str) -> bool:
    """클라우드에 있으면 내려받아 디스크에 놓는다. 성공하면 True."""
    try:
        from auth import get_supabase_client

        client = get_supabase_client(use_service_role=True)
        if not client:
            return False
        remote_audio, remote_meta = default_book_remote_keys()
        storage = client.storage.from_(AUDIOBOOK_BUCKET)
        audio = storage.download(remote_audio)
        meta = storage.download(remote_meta)
        if not audio or not meta:
            return False
        os.makedirs(DEFAULT_BOOK_DIR, exist_ok=True)
        with open(audio_path, "wb") as f:
            f.write(audio)
        with open(meta_path, "wb") as f:
            f.write(meta)
        print("Default audiobook restored from cloud.")
        return True
    except Exception as e:
        print(f"Default book not in cloud yet ({e}).")
        return False


def _upload_default_book_to_cloud(audio_path: str, meta_path: str) -> None:
    """다음 부팅부터 다시 만들지 않도록 클라우드에 올려둔다."""
    try:
        from auth import get_supabase_client

        client = get_supabase_client(use_service_role=True)
        if not client:
            return
        remote_audio, remote_meta = default_book_remote_keys()
        storage = client.storage.from_(AUDIOBOOK_BUCKET)
        with open(audio_path, "rb") as f:
            storage.upload(remote_audio, f.read(),
                           {"content-type": "audio/mpeg", "upsert": "true"})
        with open(meta_path, "rb") as f:
            storage.upload(remote_meta, f.read(),
                           {"content-type": "application/json", "upsert": "true"})
        print("Default audiobook uploaded to cloud.")
    except Exception as e:
        # 올리기 실패해도 이번 부팅에서는 이미 로컬에 있으니 서비스는 된다
        print(f"Default book cloud upload failed: {e}")


async def prepare_default_book_from_cache() -> bool:
    """합성 없이 준비만 시도한다(디스크 → 클라우드). 부팅 시 호출된다."""
    audio_path, meta_path = default_book_paths()

    if os.path.exists(audio_path) and os.path.exists(meta_path):
        default_book_state["status"] = "ready"
        print("Default audiobook already exists on disk.")
        return True

    if await asyncio.to_thread(_restore_default_book_from_cloud, audio_path, meta_path):
        default_book_state["status"] = "ready"
        return True

    # 아직 없다. 합성은 실제 요청이 올 때 한 번만 한다.
    default_book_state["status"] = "pending"
    return False


async def generate_default_book():
    """기본 제공 오디오북을 준비한다. 디스크 → 클라우드 → 생성 순으로 찾는다."""
    audio_path, meta_path = default_book_paths()

    if await prepare_default_book_from_cache():
        return

    if not os.path.exists(DEFAULT_BOOK_SOURCE):
        default_book_state["status"] = "error"
        default_book_state["error"] = "기본 제공 문서를 찾을 수 없습니다."
        print(f"Default book source missing: {DEFAULT_BOOK_SOURCE}")
        return

    default_book_state["status"] = "generating"
    print(f"Starting default audiobook generation from {DEFAULT_BOOK_SOURCE}...")
    try:
        os.makedirs(DEFAULT_BOOK_DIR, exist_ok=True)
        raw_text = extract_text(DEFAULT_BOOK_SOURCE, "demian.txt")
        # edge-tts 경로는 오디오 바이트를 돌려주므로 여기서 디스크에 쓴다
        audio_bytes, sentences, headings = await tts_routes.synthesize_document(
            raw_text, DEFAULT_BOOK_VOICE, "+5%", "+0Hz"
        )
        if not audio_bytes:
            raise RuntimeError("음성 합성 결과가 비어 있습니다.")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        del audio_bytes

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "title": DEFAULT_BOOK_TITLE,
                "sentences": sentences,
                "headings": headings,
                "char_count": len(raw_text),
            }, f, ensure_ascii=False)

        default_book_state["status"] = "ready"
        default_book_state["error"] = None
        print(f"Default book generated.")
        # 다음 부팅부터는 재합성 없이 이걸 그대로 쓴다
        await asyncio.to_thread(_upload_default_book_to_cloud, audio_path, meta_path)
    except Exception as e:
        default_book_state["status"] = "error"
        default_book_state["error"] = str(e)
        print(f"Default book generation failed: {e}")


@router.get("/api/default-book")
async def get_default_book():
    """기본 제공 오디오북의 상태 및 메타데이터를 반환.
    Edge-TTS 접속이 간헐적으로 막히는 호스팅 환경 특성상, 이전 시도가
    실패한 상태라면 요청이 들어올 때마다 재시도한다 (동시 중복 실행은 락으로 방지)."""
    audio_path, meta_path = default_book_paths()

    # pending(부팅 시 캐시에 없었음) 또는 error(이전 시도 실패)면 여기서 한 번
    # 생성한다. 부팅 시가 아니라 실제 요청 시점에 하는 이유는, 기동 직후
    # 합성을 시작하면 공유 CPU를 점유해 사용자 변환이 막히기 때문이다.
    if default_book_state["status"] in ("pending", "error"):
        async def start_generation():
            async with default_book_lock:
                if default_book_state["status"] in ("pending", "error"):
                    await generate_default_book()
        asyncio.create_task(start_generation())
        return JSONResponse(content={
            "status": "generating",
            "error": None,
        })

    if default_book_state["status"] != "ready" or not os.path.exists(meta_path):
        return JSONResponse(content={
            "status": default_book_state["status"],
            "error": default_book_state["error"],
        })

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    return JSONResponse(content={
        "status": "ready",
        "title": meta["title"],
        "sentences": meta["sentences"],
        "headings": meta.get("headings", []),
        "char_count": meta.get("char_count", 0),
        "audio_url": "/api/default-book/audio",
        "version": _default_book_fingerprint(),
    })


@router.get("/api/default-book/audio")
async def get_default_book_audio():
    audio_path, _ = default_book_paths()
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="기본 제공 오디오북이 아직 준비되지 않았습니다.")
    return FileResponse(audio_path, media_type="audio/mpeg", filename="sherlock-holmes.mp3")
