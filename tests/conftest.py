import pytest


@pytest.fixture(autouse=True)
def _reset_global_state():
    """main.py 모듈 전역의 인메모리 상태가 테스트 사이에 새어나가지 않게 한다.

    text_storage/jobs/_rate_buckets는 프로세스 전역 dict라, 한 테스트가 채운
    값이 다음 테스트에도 그대로 보여 실행 순서에 따라 결과가 달라질 수 있었다.
    """
    import main

    main._rate_buckets.clear()
    main.text_storage.clear()
    main.jobs.clear()
    yield
    main._rate_buckets.clear()
    main.text_storage.clear()
    main.jobs.clear()
