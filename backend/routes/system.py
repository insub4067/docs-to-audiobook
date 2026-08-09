"""시스템/관리자 라우트: 버전, 설정, 제품 이벤트, 관리자 지표, 정적 페이지."""
import os
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from state import (
    APP_BUILD_ID, STATIC_DIR, MAX_UPLOAD_BYTES, MAX_ADMIN_UPLOAD_BYTES,
    require_user_id, enforce_rate_limit, supabase_or_503, require_admin_user,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 클라이언트가 "사용자 경험을 안 망가뜨리려고" 조용히 삼키는 실패의 종류.
# 아무 문자열이나 받으면 오타 하나로 지표가 두 갈래로 갈라지므로,
# 새 scope를 늘릴 때는 반드시 여기에 먼저 추가한다.
CLIENT_ERROR_LABELS = {
    "playback_save": "재생 위치 저장",
    "product_event": "지표 전송",
    "generation": "오디오북 생성",
    "cloud_sync": "클라우드 동기화",
    "default_book": "기본 오디오북",
}


def _parse_event_time(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def load_admin_metrics():
    """관리자에게만 사용자·이벤트 집계와 지표별 사용자 목록을 반환한다."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    thirty_days_ago = now - timedelta(days=30)
    supabase = supabase_or_503()
    try:
        users = supabase.table("users").select("id,full_name,email,created_at").execute().data or []
        audiobooks = supabase.table("audiobooks").select("id,user_id,created_at").execute().data or []
        events = supabase.table("product_events").select("user_id,event_name,created_at") \
            .gte("created_at", thirty_days_ago.isoformat()).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"관리자 통계를 불러오지 못했습니다: {e}")

    # 조용한 실패는 여기 안 실리면 아무도 안 본다. 이 지표를 만든 이유가
    # "몇 주 동안 몰랐다"를 없애는 것이므로, 조회에 실패해도 통계 전체를
    # 죽이지 않고 빈 목록으로 둔다.
    try:
        client_errors = supabase.table("client_errors").select("user_id,scope,message,created_at") \
            .gte("created_at", week_ago.isoformat()).order("created_at", desc=True).limit(200).execute().data or []
    except Exception:
        client_errors = []

    # 가격을 정하려면 "사용자 한 명이 얼마를 쓰는가"를 알아야 한다. 이 표가
    # 비어 있으면 요금제는 감으로 정하는 수밖에 없다.
    try:
        usage = supabase.table("synthesis_usage").select("user_id,provider,characters,audio_seconds,succeeded,created_at") \
            .gte("created_at", thirty_days_ago.isoformat()).execute().data or []
    except Exception:
        usage = []

    dated_events = [(event, _parse_event_time(event.get("created_at"))) for event in events]
    recent_events = [(event, event_time) for event, event_time in dated_events if event_time]
    weekly_active_users = {event["user_id"] for event, event_time in recent_events if event_time >= week_ago}
    daily_active_users = {event["user_id"] for event, event_time in recent_events if event_time >= now - timedelta(days=1)}
    started = sum(event["event_name"] == "generation_started" for event, _ in recent_events)
    completed = sum(event["event_name"] == "generation_completed" for event, _ in recent_events)
    failed = sum(event["event_name"] == "generation_failed" for event, _ in recent_events)

    first_event_by_user = {}
    for event, event_time in recent_events:
        user_id = event.get("user_id")
        if user_id and (user_id not in first_event_by_user or event_time < first_event_by_user[user_id]):
            first_event_by_user[user_id] = event_time
    week_one_cohort = {
        user_id for user_id, event_time in first_event_by_user.items()
        if two_weeks_ago <= event_time < week_ago
    }
    returning_users = {
        event["user_id"] for event, event_time in recent_events
        if event_time >= week_ago and event.get("user_id") in week_one_cohort
    }

    users_by_id = {user["id"]: user for user in users}

    def user_list(user_ids, meta_by_id=None):
        people = []
        for user_id in user_ids:
            user = users_by_id.get(user_id)
            if not user:
                continue
            people.append({
                "name": user.get("full_name") or "이름 없음",
                "email": user.get("email") or "",
                "meta": (meta_by_id or {}).get(user_id, ""),
            })
        return sorted(people, key=lambda person: (person["name"], person["email"]))

    generation_counts = {}
    playback_counts = {}
    for event, _ in recent_events:
        user_id = event.get("user_id")
        if not user_id:
            continue
        if event["event_name"] in {"generation_completed", "generation_failed"}:
            counts = generation_counts.setdefault(user_id, {"completed": 0, "failed": 0})
            counts["completed" if event["event_name"] == "generation_completed" else "failed"] += 1
        if event["event_name"] == "playback_started":
            playback_counts[user_id] = playback_counts.get(user_id, 0) + 1

    # 문자 수만 쌓아 두고 금액은 여기서 곱한다. 단가는 바뀌므로 파생값을
    # DB에 굳히지 않는다. edge_tts는 비공식 무료 엔드포인트라 0이고, 지금
    # 카탈로그의 두 음성은 모두 edge_tts다 — 즉 현재 TTS 한계비용은 0이다.
    # google 단가는 Cloud TTS 요금표를 보고 갱신할 것(2026-08 기준 추정치).
    usd_per_million_chars = {"edge_tts": 0.0, "google": 16.0}
    usage_by_user = {}
    total_characters = 0
    estimated_usd = 0.0
    failed_characters = 0
    for row in usage:
        characters = int(row.get("characters") or 0)
        rate = usd_per_million_chars.get(row.get("provider"), 0.0)
        total_characters += characters
        estimated_usd += characters / 1_000_000 * rate
        if not row.get("succeeded", True):
            failed_characters += characters
        user_id = row.get("user_id")
        if user_id:
            bucket = usage_by_user.setdefault(user_id, {"characters": 0, "audio_seconds": 0.0, "runs": 0})
            bucket["characters"] += characters
            bucket["audio_seconds"] += float(row.get("audio_seconds") or 0)
            bucket["runs"] += 1

    audiobook_counts = {}
    for audiobook in audiobooks:
        user_id = audiobook.get("user_id")
        if user_id:
            audiobook_counts[user_id] = audiobook_counts.get(user_id, 0) + 1

    metric_details = {
        "total_users": user_list(
            users_by_id,
            {user["id"]: f"가입일 {str(user.get('created_at') or '')[:10]}" for user in users},
        ),
        "daily_active_users": user_list(daily_active_users, {user_id: "최근 24시간 활동" for user_id in daily_active_users}),
        "weekly_active_users": user_list(weekly_active_users, {user_id: "최근 7일 활동" for user_id in weekly_active_users}),
        "week_one_retention_rate": user_list(
            week_one_cohort,
            {user_id: "재방문" if user_id in returning_users else "미재방문" for user_id in week_one_cohort},
        ),
        "generation_success_rate": user_list(
            generation_counts,
            {
                user_id: f"완료 {counts['completed']}회 · 실패 {counts['failed']}회"
                for user_id, counts in generation_counts.items()
            },
        ),
        "playback_started_30d": user_list(
            playback_counts,
            {user_id: f"재생 시작 {count}회" for user_id, count in playback_counts.items()},
        ),
        "total_audiobooks": user_list(
            audiobook_counts,
            {user_id: f"오디오북 {count}권" for user_id, count in audiobook_counts.items()},
        ),
        "synthesis_characters_30d": user_list(
            usage_by_user,
            {
                user_id: f"{bucket['characters']:,}자 · 오디오 {round(bucket['audio_seconds'] / 60):,}분 · {bucket['runs']}회"
                for user_id, bucket in usage_by_user.items()
            },
        ),
        # 이 목록만 사람이 아니라 사건이다. 상세 화면의 세 칸(name/email/meta)에
        # 각각 범위·발생자·내용을 싣는다 — 칸 하나를 위해 화면을 새로 만들 만큼
        # 자주 볼 지표가 아니다.
        "client_errors_7d": [
            {
                "name": CLIENT_ERROR_LABELS.get(error.get("scope"), error.get("scope") or "알 수 없음"),
                "email": (users_by_id.get(error.get("user_id"), {}).get("email") or "비로그인"),
                "meta": f"{str(error.get('created_at') or '')[5:16].replace('T', ' ')} · {error.get('message') or ''}",
            }
            for error in client_errors
        ],
    }

    return {
        "total_users": len(users),
        "new_users_7d": sum((_parse_event_time(user.get("created_at")) or now) >= week_ago for user in users),
        "total_audiobooks": len(audiobooks),
        "daily_active_users": len(daily_active_users),
        "weekly_active_users": len(weekly_active_users),
        "generation_started_30d": started,
        "generation_completed_30d": completed,
        "generation_failed_30d": failed,
        "generation_success_rate": round(completed / (completed + failed) * 100) if completed + failed else None,
        "playback_started_30d": sum(event["event_name"] == "playback_started" for event, _ in recent_events),
        "play_5min_30d": sum(event["event_name"] == "play_5min" for event, _ in recent_events),
        "week_one_retention_rate": round(len(returning_users) / len(week_one_cohort) * 100) if week_one_cohort else None,
        "retention_cohort_size": len(week_one_cohort),
        "client_errors_7d": len(client_errors),
        "synthesis_characters_30d": total_characters,
        "synthesis_failed_characters_30d": failed_characters,
        "synthesis_estimated_usd_30d": round(estimated_usd, 2),
        # 요금제를 정할 때 보는 값. 활성 사용자 한 명이 30일간 만드는 TTS 비용이다.
        "tts_cost_per_active_user_usd": (
            round(estimated_usd / len(weekly_active_users), 4) if weekly_active_users else None
        ),
        "metric_details": metric_details,
    }


@router.get("/api/version")
async def get_version():
    """Returns the server's build ID. Client polls this on foreground resume to detect redeployment."""
    return JSONResponse(content={"build_id": APP_BUILD_ID})


@router.get("/api/config")
async def get_config():
    """클라이언트 설정. 소셜 로그인 클라이언트 ID는 브라우저에 노출되는 공개
    값이라 코드에 박지 않고 환경변수에서 내려준다(그동안 플레이스홀더가 박혀
    있어 로그인이 아예 동작하지 않았다).

    제공자를 늘릴 때는 아래 dict에 한 줄만 추가하면 된다. 값이 비어 있는
    제공자는 클라이언트가 알아서 건너뛴다."""
    providers = {
        "google": os.getenv("GOOGLE_CLIENT_ID", ""),
        # "kakao": os.getenv("KAKAO_JS_KEY", ""),
        # "naver": os.getenv("NAVER_CLIENT_ID", ""),
        # "apple": os.getenv("APPLE_CLIENT_ID", ""),
    }
    return JSONResponse(content={
        "providers": {k: v for k, v in providers.items() if v},
        # 이전 클라이언트 호환용
        "google_client_id": providers.get("google", ""),
        # 업로드 상한의 단일 출처. 예전에는 프론트가 같은 숫자를 따로
        # 들고 있었고, 실제로 어긋나 있었다(관리자 상한이 백엔드 250MB인데
        # 프론트가 50MB로 막았다). 상한은 비밀이 아니라 인증 없이 내려준다 —
        # 실제 강제는 어차피 업로드 스트림에서 서버가 한다.
        "upload_limit_bytes": MAX_UPLOAD_BYTES,
        "admin_upload_limit_bytes": MAX_ADMIN_UPLOAD_BYTES,
        # 구글 드라이브 가져오기(Picker)용 공개 API 키. Picker API 자체는
        # OAuth 토큰만으로도 대부분 동작하지만, 구글 문서상 권장 조합이라
        # 설정돼 있으면 함께 내려준다 — 없어도 기능은 그대로 동작한다.
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
    })


@router.post("/api/events")
async def create_product_event(request: Request, payload: dict, authorization: str = Header(None)):
    """개인 콘텐츠 없이 제품 이용 지표에 필요한 이벤트만 기록한다."""
    user_id = require_user_id(authorization)
    enforce_rate_limit(request, "product_event", limit=120, window_sec=600)
    event_name = payload.get("event_name")
    if event_name not in {"generation_started", "generation_completed", "generation_failed", "playback_started", "play_5min"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 이벤트입니다.")
    try:
        supabase_or_503().table("product_events").insert({
            "user_id": user_id,
            "event_name": event_name,
        }).execute()
        return {"recorded": event_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"이벤트를 기록하지 못했습니다: {e}")


CLIENT_ERROR_MESSAGE_LIMIT = 500


@router.post("/api/client-errors")
async def create_client_error(request: Request, payload: dict, authorization: str = Header(None)):
    """클라이언트가 삼킨 실패를 한 줄 남긴다.

    ⚠️ 로그인 여부를 따지지 않는다. 가입만 하고 아무것도 안 한 사용자가
    무엇에 걸려 떠났는지가 정확히 여기서 알고 싶은 것이라, 비로그인 체험 중의
    실패를 버리면 이 엔드포인트를 만든 이유의 절반이 사라진다.

    또 이 엔드포인트는 실패해도 예외를 밖으로 던지지 않는다. 실패 보고가
    실패해서 500을 내면 클라이언트가 그걸 또 삼키고, 결국 같은 침묵이
    한 겹 더 생긴다. DB가 죽어 있어도 stdout에는 반드시 남긴다."""
    enforce_rate_limit(request, "client_error", limit=60, window_sec=600)
    scope = payload.get("scope")
    if scope not in CLIENT_ERROR_LABELS:
        raise HTTPException(status_code=400, detail="지원하지 않는 오류 범위입니다.")
    message = str(payload.get("message") or "")[:CLIENT_ERROR_MESSAGE_LIMIT]
    if not message:
        raise HTTPException(status_code=400, detail="오류 내용이 비어 있습니다.")

    user_id = None
    if authorization:
        try:
            user_id = require_user_id(authorization)
        except HTTPException:
            # 토큰이 만료된 채로 보내는 것도 흔하다. 그렇다고 보고를 버리진 않는다.
            user_id = None

    logger.warning("[client-error] scope=%s user=%s %s", scope, user_id or "anonymous", message)
    try:
        supabase_or_503().table("client_errors").insert({
            "user_id": user_id,
            "scope": scope,
            "message": message,
            # 클라이언트가 아니라 보고를 받은 서버의 빌드다. 클라이언트는 자기
            # 버전을 확실히 알 방법이 없고(캐시된 sw.js를 다시 읽을 수 없다),
            # 실무에서 필요한 건 "어느 배포부터 이 오류가 시작됐나"라 이걸로 충분하다.
            "app_version": APP_BUILD_ID,
        }).execute()
    except Exception as e:
        logger.warning("[client-error] 저장 실패: %s", e)
    return {"recorded": scope}


@router.get("/api/admin/metrics")
async def get_admin_metrics(authorization: str = Header(None)):
    require_admin_user(authorization)
    return load_admin_metrics()


@router.get("/manifest.json")
async def get_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/json")


@router.get("/sw.js")
async def get_serviceworker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


@router.get("/")
async def read_index():
    # Vite로 빌드된 메인 SPA(frontend/app.html). admin.html과 마찬가지로
    # base: "/static/dist/app/"라 자산 경로는 이 라우트 위치와 무관하다.
    app_path = os.path.join(STATIC_DIR, "dist", "app", "app.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)
    return JSONResponse(status_code=404, content={"message": "Frontend build not found. Build the frontend first."})


@router.get("/admin")
async def read_admin_dashboard():
    # Vite로 빌드된 결과물(frontend/Admin). 자산 경로가 절대경로로
    # 박혀 있어(base: "/static/dist/admin/") 이 라우트가 파일을 어디서
    # 읽어오든 상관없이 그대로 서빙할 수 있다.
    admin_path = os.path.join(STATIC_DIR, "dist", "admin", "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return JSONResponse(status_code=404, content={"message": "관리자 대시보드를 찾을 수 없습니다."})


@router.get("/admin/metrics/{metric_name}")
async def read_admin_metric_page(metric_name: str):
    metric_path = os.path.join(STATIC_DIR, "admin-metric.html")
    if os.path.exists(metric_path):
        return FileResponse(metric_path)
    return JSONResponse(status_code=404, content={"message": "관리자 지표 화면을 찾을 수 없습니다."})
