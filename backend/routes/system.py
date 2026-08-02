"""시스템/관리자 라우트: 버전, 설정, 제품 이벤트, 관리자 지표, 정적 페이지."""
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from state import APP_BUILD_ID, STATIC_DIR, require_user_id, enforce_rate_limit, _supabase_or_503, require_admin_user

router = APIRouter()


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
    supabase = _supabase_or_503()
    try:
        users = supabase.table("users").select("id,full_name,email,created_at").execute().data or []
        audiobooks = supabase.table("audiobooks").select("id,user_id,created_at").execute().data or []
        events = supabase.table("product_events").select("user_id,event_name,created_at") \
            .gte("created_at", thirty_days_ago.isoformat()).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"관리자 통계를 불러오지 못했습니다: {e}")

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
        "week_one_retention_rate": round(len(returning_users) / len(week_one_cohort) * 100) if week_one_cohort else None,
        "retention_cohort_size": len(week_one_cohort),
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
        "google_client_id": providers.get("google", "")
    })


@router.post("/api/events")
async def create_product_event(request: Request, payload: dict, authorization: str = Header(None)):
    """개인 콘텐츠 없이 제품 이용 지표에 필요한 이벤트만 기록한다."""
    user_id = require_user_id(authorization)
    enforce_rate_limit(request, "product_event", limit=120, window_sec=600)
    event_name = payload.get("event_name")
    if event_name not in {"generation_started", "generation_completed", "generation_failed", "playback_started"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 이벤트입니다.")
    try:
        _supabase_or_503().table("product_events").insert({
            "user_id": user_id,
            "event_name": event_name,
        }).execute()
        return {"recorded": event_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"이벤트를 기록하지 못했습니다: {e}")


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
