# 트러블슈팅 기록

실제로 겪은 문제와 해결 과정을 남긴다. 목적은 "이게 어떻게 동작한다"가 아니라
"이런 증상을 다시 보면 이 원인부터 의심하라"는 기록이다. 각 문서는 증상 → 원인 →
해결 → 교훈 순서로 쓴다.

## 목록

| 문서 | 증상 한 줄 | 영역 |
|---|---|---|
| [01-ios-session-drop.md](01-ios-session-drop.md) | iOS PWA에서 로그인이 저절로 풀림 | 인증 |
| [02-default-book-chapter-cache.md](02-default-book-chapter-cache.md) | 기본 제공 오디오북이 챕터 3개만 나옴 | 캐시 무효화 |
| [03-test-suite-corrupted-app-js.md](03-test-suite-corrupted-app-js.md) | 테스트를 돌렸더니 실서비스 파일이 깨짐 | 테스트 안전 |
| [04-vacuous-delete-test.md](04-vacuous-delete-test.md) | 통과하는 테스트가 실제로는 아무것도 검증 안 함 | 테스트 신뢰성 |
| [05-app-js-scope-split-bug.md](05-app-js-scope-split-bug.md) | 특정 순서로만 앱 초기화가 조용히 멈춤 | 프론트엔드 구조 |
| [06-ci-missing-commit-confusion.md](06-ci-missing-commit-confusion.md) | CI가 계속 실패하는데 로컬은 통과함 | CI/CD |
| [07-admin-char-limit-static-vs-dynamic.md](07-admin-char-limit-static-vs-dynamic.md) | 관리자 대용량 문서 상한에 반복해서 걸림 | 용량 설계 |
| [08-admin-job-reliability.md](08-admin-job-reliability.md) | 대용량 합성 작업이 통째로 날아가거나 고아 레코드를 남김 | 신뢰성 |
| [09-pdf-garbled-extraction.md](09-pdf-garbled-extraction.md) | PDF에서 뽑은 텍스트가 "G G GG G" 식으로 깨짐 | 파일 파싱 |
| [10-pdf-parsing-blocks-event-loop.md](10-pdf-parsing-blocks-event-loop.md) | 큰 파일 업로드 중 다른 사용자 요청이 전부 멈춤 | 동시성 |

## 공통 교훈

- **고정 숫자보다 실측**: "안전할 것 같은 상수"를 추측하지 말고, 가능하면 그 순간의
  실제 상태(디스크 여유 등)를 재서 판단한다(07).
- **테스트가 통과한다 ≠ 회귀를 잡는다**: 새 테스트를 추가하면 일부러 로직을 깨서
  실제로 실패하는지 확인한 뒤 원복하는 걸 이 프로젝트의 기본 절차로 삼는다(03, 04, 08, 09).
- **스코프 경계는 눈에 보여야 한다**: 코드를 훑어봐서 안 보이는 경계(전역 vs 클로저,
  커밋 vs 미커밋)가 반복해서 사고를 냈다(05, 06).
- **동기 호출이 이벤트 루프를 막을 수 있다는 걸 항상 의심한다**: 단일 인스턴스·단일
  이벤트 루프 구조라, 무거운 동기 작업 하나가 전체 서비스를 멈출 수 있다(10).
