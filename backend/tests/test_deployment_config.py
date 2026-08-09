"""배포 설정 가드.

코드가 아니라 배포 파이프라인의 성질을 고정한다. 여기 있는 두 규칙은 둘 다
"조용히 되돌려도 아무도 모르는" 종류라(테스트가 깨지지 않고, 화면도 그대로다)
설정 파일에 주석만 남겨서는 지켜지지 않는다.
"""
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT_DIR / ".github" / "workflows" / "ci-cd.yaml"
DOCKERIGNORE = ROOT_DIR / ".dockerignore"
DOCKERFILE = ROOT_DIR / "Dockerfile"


def _job_block(name: str) -> str:
    """워크플로에서 해당 잡의 본문만 잘라낸다.

    PyYAML을 테스트 전용으로 새로 들이는 대신 들여쓰기로 자른다 — 잡 정의는
    항상 두 칸 들여쓰기이고, 다음 잡은 같은 깊이에서 시작한다.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"  {name}:"))
    block = []
    for line in lines[start + 1:]:
        if re.match(r"^  \S", line):  # 같은 깊이의 다음 잡
            break
        block.append(line)
    return "\n".join(block)


def test_deploy_waits_for_tests():
    """예전에는 deploy가 test와 병렬로 돌아, 테스트·빌드·린트가 깨진 커밋도
    그대로 프로덕션에 나갔다."""
    deploy = _job_block("deploy")

    assert re.search(r"^\s*needs:\s*(test\b|\[.*\btest\b.*\])", deploy, re.M), \
        "deploy 잡에 needs: test가 없다 — 테스트 실패해도 배포된다"


def test_dockerignore_keeps_secrets_and_local_junk_out_of_the_image():
    """Dockerfile이 저장소 전체를 COPY하는데 .gitignore는 빌드 컨텍스트에
    아무 영향이 없다. 개발 머신에서 직접 flyctl deploy하면 로컬 .env가
    그대로 이미지에 실린다."""
    assert re.search(r"^COPY\b.*\s\.\s+\$HOME/app\s*$", DOCKERFILE.read_text(encoding="utf-8"), re.M), \
        "Dockerfile이 더 이상 저장소 전체를 COPY하지 않는다면 이 가드도 다시 봐야 한다."

    ignored = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    for required in [".env", "backend/.env", ".venv/", "frontend/node_modules/"]:
        assert required in ignored, f".dockerignore에 {required}가 없다"


def test_dockerignore_keeps_files_the_app_actually_needs():
    """제외 규칙이 너무 넓어지면 런타임에 필요한 파일까지 빠진다 —
    기본 제공 오디오북 원문(demian.txt)이 대표적이다."""
    ignored = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    for kept in ["backend/", "frontend/static/samples/", "frontend/static/"]:
        assert kept not in ignored
