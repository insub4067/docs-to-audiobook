import os
from unittest.mock import MagicMock, patch

import pytest


os.environ.setdefault("SECRET_KEY", "test-secret-key")


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """supabase-py의 체이닝 흉내. eq("id", ...)만 실제로 해석한다."""

    def __init__(self, table, op, payload=None, columns="*"):
        self.table = table
        self.op = op
        self.payload = payload
        self.columns = columns
        self.job_id = None

    def eq(self, column, value):
        if column == "id":
            self.job_id = value
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return self.table._execute(self)


class FakeContentJobsTable:
    """content_jobs 테이블의 최소 구현.

    MagicMock으로 행을 하나 고정해두면 "등록 → 처리기가 다시 읽음 → 완료 시
    삭제"라는 실제 흐름이 검증되지 않는다. insert한 행을 그대로 기억했다가
    돌려줘서 등록 경로가 통째로 돌게 한다.
    """

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.inserted: list[dict] = []
        self.updates: list[tuple[str | None, dict]] = []
        self.deleted: list[str | None] = []
        self.selected_columns: str | None = None

    def insert(self, row):
        self.rows[row["id"]] = {"status": "queued", "error": None, **row}
        self.inserted.append(row)
        return _Query(self, "insert")

    def select(self, columns="*"):
        self.selected_columns = columns
        return _Query(self, "select", columns=columns)

    def update(self, patch):
        return _Query(self, "update", patch)

    def delete(self):
        return _Query(self, "delete")

    def _execute(self, query):
        if query.op == "select":
            if query.job_id is not None:
                return _Result(self.rows.get(query.job_id))
            return _Result([dict(row) for row in self.rows.values()])
        if query.op == "update":
            self.updates.append((query.job_id, query.payload))
            if query.job_id in self.rows:
                self.rows[query.job_id].update(query.payload)
        elif query.op == "delete":
            self.deleted.append(query.job_id)
            self.rows.pop(query.job_id, None)
        return _Result(None)

    def status_updates(self):
        return [patch.get("status") for _job_id, patch in self.updates if "status" in patch]


@pytest.fixture
def mock_supabase_tables():
    """테이블 이름별로 다른 목을 돌려주는 supabase 클라이언트.

    등록 경로는 content_jobs(작업)와 audiobooks(완성물) 두 테이블을 함께
    건드린다. 하나의 목을 공유하면 어느 테이블에 무엇을 넣었는지 구분할 수
    없어 검증이 무의미해진다. 반환값은 (client, tables)이고 tables["content_jobs"]는
    FakeContentJobsTable이다.
    """
    with patch("auth.get_supabase_client") as get_client:
        client = MagicMock()
        tables: dict[str, object] = {"content_jobs": FakeContentJobsTable()}
        client.table.side_effect = lambda name: tables.setdefault(name, MagicMock())
        get_client.return_value = client
        yield client, tables


def rows_inserted_into(tables, table_name):
    """해당 테이블에 insert된 행들. content_jobs는 FakeContentJobsTable이 기억한다."""
    mock = tables.get(table_name)
    if mock is None:
        return []
    if isinstance(mock, FakeContentJobsTable):
        return mock.inserted
    return [call.args[0] for call in mock.insert.call_args_list if call.args]


@pytest.fixture(autouse=True)
def _reset_global_state():
    """state.py 모듈 전역의 인메모리 상태가 테스트 사이에 새어나가지 않게 한다.

    text_storage/jobs/_rate_buckets는 프로세스 전역 dict라, 한 테스트가 채운
    값이 다음 테스트에도 그대로 보여 실행 순서에 따라 결과가 달라질 수 있었다.
    """
    import state

    state._rate_buckets.clear()
    state.text_storage.clear()
    state.jobs.clear()
    yield
    state._rate_buckets.clear()
    state.text_storage.clear()
    state.jobs.clear()
