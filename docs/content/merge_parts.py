#!/usr/bin/env python3
"""배치로 나눠 뽑은 부 원고를 등록용 JSON 하나로 합친다.

코덱스에 24권을 한 번에 시키면 뒤로 갈수록 분량이 무너져서, 4권씩 여섯 번
나눠 뽑는다. 이 스크립트는 그 결과(parts/batch*.json)를 part_number 순으로
이어 붙여 /api/admin/library에 그대로 붙여넣을 형태로 만든다.

    python3 docs/content/merge_parts.py

입력: docs/content/parts/batch*.json
      [{"part_number": 1, "title": "제1권 · ...", "content": "..."}, ...]
출력: docs/content/odyssey-full.json

⚠️ 기존 odyssey.json(부당 640자짜리 첫 버전)은 덮어쓰지 않는다. 새 원고가
   마음에 안 들 때 되돌릴 자리가 필요하다.
"""
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).parent
PARTS_DIR = BASE / "parts"
OUTPUT = BASE / "odyssey-full.json"

# 작품 메타는 부와 달리 배치마다 반복되지 않으므로 여기 한 벌만 둔다.
WORK = {
    "title": "오디세이",
    "category": "고전문학",
    "description": "트로이아 전쟁을 끝낸 영웅 오디세우스가 수많은 시련과 유혹을 헤치고 "
                   "고향 이타케와 가족에게 돌아가기까지 약 십 년의 여정을 그린 고대 그리스 서사시.",
    "edition": "오디오북용 한국어 재서술본 · 전 24권",
    "translator": "",
    "source": "호메로스 『오디세이』 원전 기반 재서술",
    "rights": "고대 원전 퍼블릭 도메인 · 본문은 AI를 활용해 새롭게 재서술",
    # ⚠️ review로 둔다. 판본과 이용 근거를 사람이 직접 확인한 뒤에만 관리자
    #    화면에서 published로 바꾼다(routes/library.py 첫머리의 원칙).
    "status": "review",
}


def main() -> int:
    batches = sorted(PARTS_DIR.glob("batch*.json"))
    if not batches:
        print(f"부 원고를 찾지 못했습니다: {PARTS_DIR}/batch*.json", file=sys.stderr)
        return 1

    parts = []
    for path in batches:
        parts.extend(json.loads(path.read_text()))

    # 배치 파일 이름이 아니라 part_number로 정렬한다. 파일명은 사람이 붙인
    # 것이라 "9~12"가 "13~16"보다 뒤로 갈 수 있다.
    parts.sort(key=lambda part: part["part_number"])

    numbers = [part["part_number"] for part in parts]
    if numbers != list(range(1, len(numbers) + 1)):
        missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        duplicated = sorted({n for n in numbers if numbers.count(n) > 1})
        print(f"부 번호가 이어지지 않습니다. 빠짐={missing} 중복={duplicated}", file=sys.stderr)
        return 1

    work = {**WORK, "parts": [
        {"title": part["title"], "content": part["content"]} for part in parts
    ]}
    OUTPUT.write_text(json.dumps([work], ensure_ascii=False, indent=2) + "\n")

    total = sum(len(part["content"]) for part in parts)
    print(f"{OUTPUT.name} — {len(parts)}부 · {total:,}자 · 예상 {total / 350 / 60:.1f}시간")
    for part in parts:
        print(f"  {part['part_number']:>2}. {part['title'][:32]:34s} {len(part['content']):>6,}자")
    return 0


if __name__ == "__main__":
    sys.exit(main())
