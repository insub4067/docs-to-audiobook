"""TTS 사용량 기록 테스트.

가격을 정하려면 "사용자 한 명이 얼마를 쓰는가"를 알아야 하는데, 지금까지
product_events에는 user_id와 event_name밖에 없어 그 계산이 불가능했다.
여기서 지켜야 할 불변조건은 둘이다.

1. 합성이 끝나면(성공이든 실패든) 문자 수가 남는다.
2. 기록이 실패해도 합성은 멀쩡하다 — 지표는 부수적이고 오디오가 본체다.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.conftest import rows_inserted_into
from main import app
from routes import tts
from state import jobs


def _hours_ago(hours: int) -> str:
    """지금으로부터 N시간 전. 지표 테스트의 시각은 반드시 상대값으로 만든다.

    ⚠️ 예전에는 "2026-08-08T12:00:00+00:00" 같은 고정 날짜를 썼는데, 주간
    활성 사용자는 최근 7일만 세므로(routes/system.py의 week_ago) 그 날짜가
    일주일을 넘기는 순간 테스트가 스스로 깨졌다. 실제로 그렇게 깨져서 관계
    없는 PR의 CI를 막았다 — 코드는 그대로였고 달력만 넘어갔을 뿐이다.
    """
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _auth_headers(user_id="test_user_id"):
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


def _seed_job(job_id, user_id="user-1"):
    jobs[job_id] = {
        "status": "processing", "user_id": user_id, "chunk_durations": [90_000, 30_000],
        "sentences": [], "headings": [], "display_markdown": "", "audio_path": None,
        "ready_chunks": 0, "completed_chunks": 0, "total_chunks": 0, "error": None,
    }


@pytest.mark.asyncio
async def test_records_characters_and_audio_length(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    _seed_job("job-usage")

    tts._record_synthesis_usage("job-usage", "가" * 4200, "ko_male_warm", 12.345, succeeded=True)

    rows = rows_inserted_into(tables, "synthesis_usage")
    assert len(rows) == 1
    assert rows[0]["characters"] == 4200
    assert rows[0]["user_id"] == "user-1"
    assert rows[0]["voice"] == "ko_male_warm"
    # 카탈로그가 음성별로 공급자를 고정한다. 지금 두 음성은 모두 edge_tts다.
    assert rows[0]["provider"] == "edge_tts"
    # chunk_durations는 밀리초다(120,000ms = 120초).
    assert float(rows[0]["audio_seconds"]) == 120.0
    assert float(rows[0]["elapsed_seconds"]) == 12.35
    assert rows[0]["succeeded"] is True
    del jobs["job-usage"]


@pytest.mark.asyncio
async def test_records_failed_synthesis_too(mock_supabase_tables):
    """⚠️ 실패한 합성도 문자를 소모한다. 성공만 세면 실비용을 과소평가한다 —
    Edge TTS는 호스트에 따라 간헐적으로 실패하므로 이 차이가 작지 않다."""
    _client, tables = mock_supabase_tables
    _seed_job("job-failed")

    tts._record_synthesis_usage("job-failed", "나" * 900, "ko_female_calm", 3.0, succeeded=False)

    rows = rows_inserted_into(tables, "synthesis_usage")
    assert len(rows) == 1
    assert rows[0]["characters"] == 900
    assert rows[0]["succeeded"] is False
    del jobs["job-failed"]


@pytest.mark.asyncio
async def test_usage_recording_failure_does_not_raise(mock_supabase_tables):
    """기록이 합성을 망치면 안 된다. 여기서 예외가 새면 이미 만들어 둔
    오디오가 error 상태로 뒤집혀 사용자가 결과를 잃는다."""
    _client, tables = mock_supabase_tables
    broken = MagicMock()
    broken.insert.side_effect = RuntimeError("supabase down")
    tables["synthesis_usage"] = broken
    _seed_job("job-broken")

    tts._record_synthesis_usage("job-broken", "다" * 10, "ko_male_warm", 1.0, succeeded=True)

    del jobs["job-broken"]


@pytest.mark.asyncio
async def test_no_audio_yet_records_null_duration(mock_supabase_tables):
    """청크가 하나도 안 나온 채 실패하면 오디오 길이가 없다. 0으로 적으면
    "0초짜리 오디오를 만들었다"가 되어 평균 길이를 왜곡한다."""
    _client, tables = mock_supabase_tables
    jobs["job-empty"] = {"status": "processing", "user_id": "user-2", "chunk_durations": []}

    tts._record_synthesis_usage("job-empty", "라" * 50, "ko_male_warm", 0.5, succeeded=False)

    rows = rows_inserted_into(tables, "synthesis_usage")
    assert rows[0]["audio_seconds"] is None
    del jobs["job-empty"]


@pytest.mark.asyncio
async def test_synthesis_path_actually_records(mock_supabase_tables):
    """⚠️ 위 테스트들은 _record_synthesis_usage를 직접 부른다. 그래서 함수가
    합성 경로에 물려 있는지는 증명하지 못한다 — 호출부를 전부 지워도 통과한다.
    여기서만 process_synthesis_task를 통째로 태워 배선을 확인한다."""
    _client, tables = mock_supabase_tables
    jobs["job-wired"] = {"status": "processing", "user_id": "user-3", "chunk_durations": []}

    async def fake_synthesize(*_args, **_kwargs):
        return [], [], ""

    with patch("routes.tts.synthesize_document_to_file", side_effect=fake_synthesize):
        await tts.process_synthesis_task("job-wired", "마" * 777, "ko_male_warm", "+0%", "+0Hz")

    rows = rows_inserted_into(tables, "synthesis_usage")
    assert len(rows) == 1, "합성이 끝났는데 사용량이 남지 않았다"
    assert rows[0]["characters"] == 777
    # 파일이 안 생겼으므로 실패로 끝난다 — 그 경로에서도 기록돼야 한다.
    assert rows[0]["succeeded"] is False
    del jobs["job-wired"]


@pytest.mark.asyncio
async def test_synthesis_success_path_records(mock_supabase_tables, tmp_path, monkeypatch):
    """성공 경로도 같은 이유로 실제 함수를 태워 확인한다."""
    _client, tables = mock_supabase_tables
    monkeypatch.setattr("routes.tts.JOB_AUDIO_DIR", str(tmp_path))
    jobs["job-wired-ok"] = {"status": "processing", "user_id": "user-4", "chunk_durations": [60_000]}

    async def fake_synthesize(_text, _voice, _rate, _pitch, output_path, **_kwargs):
        with open(output_path, "wb") as f:
            f.write(b"audio-bytes")
        return [], [], ""

    with patch("routes.tts.synthesize_document_to_file", side_effect=fake_synthesize):
        await tts.process_synthesis_task("job-wired-ok", "바" * 1234, "ko_female_calm", "+0%", "+0Hz")

    assert jobs["job-wired-ok"]["status"] == "completed"
    rows = rows_inserted_into(tables, "synthesis_usage")
    assert len(rows) == 1
    assert rows[0]["characters"] == 1234
    assert rows[0]["succeeded"] is True
    assert float(rows[0]["audio_seconds"]) == 60.0
    del jobs["job-wired-ok"]


@pytest.mark.asyncio
async def test_metrics_expose_cost_per_active_user(mock_supabase_tables):
    """관리자 지표에 안 실리면 아무도 안 본다 — 요금제를 정할 때 볼 값이다."""
    _client, tables = mock_supabase_tables
    usage = MagicMock()
    usage.select.return_value.gte.return_value.execute.return_value.data = [
        {"user_id": "u1", "provider": "google", "characters": 1_000_000,
         "audio_seconds": 3600, "succeeded": True, "created_at": _hours_ago(30)},
        {"user_id": "u1", "provider": "edge_tts", "characters": 500_000,
         "audio_seconds": 1800, "succeeded": False, "created_at": _hours_ago(29)},
    ]
    tables["synthesis_usage"] = usage
    events = MagicMock()
    events.select.return_value.gte.return_value.execute.return_value.data = [
        {"user_id": "u1", "event_name": "playback_started", "created_at": _hours_ago(28)},
    ]
    tables["product_events"] = events
    for name in ("users", "audiobooks"):
        tables[name] = MagicMock()
        tables[name].select.return_value.execute.return_value.data = []
        tables[name].select.return_value.gte.return_value.execute.return_value.data = []
    errors = MagicMock()
    errors.select.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    tables["client_errors"] = errors

    with patch("routes.system.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/api/admin/metrics", headers=_auth_headers())

    body = response.json()
    assert body["synthesis_characters_30d"] == 1_500_000
    assert body["synthesis_failed_characters_30d"] == 500_000
    # edge_tts는 비공식 무료 엔드포인트라 0. google 100만 자만 금액이 붙는다.
    assert body["synthesis_estimated_usd_30d"] == 16.0
    # 주간 활성 사용자 1명이 만든 비용.
    assert body["tts_cost_per_active_user_usd"] == 16.0


@pytest.mark.asyncio
async def test_metrics_survive_usage_query_failure(mock_supabase_tables):
    """사용량 표가 아직 없거나 조회가 깨져도 관리자 통계 전체가 죽으면 안 된다."""
    _client, tables = mock_supabase_tables
    broken = MagicMock()
    broken.select.side_effect = RuntimeError("relation does not exist")
    tables["synthesis_usage"] = broken
    for name in ("users", "audiobooks", "product_events"):
        tables[name] = MagicMock()
        tables[name].select.return_value.execute.return_value.data = []
        tables[name].select.return_value.gte.return_value.execute.return_value.data = []
    errors = MagicMock()
    errors.select.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    tables["client_errors"] = errors

    with patch("routes.system.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/api/admin/metrics", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["synthesis_characters_30d"] == 0
