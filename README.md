---
title: Docs To Audiobook
emoji: 🎧
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Docs to Audiobook Converter

FastAPI + Vanilla JS Audiobook generator utilizing Edge TTS, supporting smart text chunking, voice filtering, and client-side IndexedDB persistent storage.

## 🚀 Features

- **문서 변환**: DOCX, PDF, TXT, MD, HWP 지원
- **음성 선택**: 7개 한국어 음성 + 필터링 (tone, use_case)
- **기본 제공**: 셜록 홈즈의 모험 자동 다운로드 & 오프라인 재생
- **신뢰성**: 청크 단위 재시도로 간헐적 네트워크 오류 극복
- **동기화**: 기본 오디오북 상단 고정, 자동 갱신
- **PWA**: 온/오프라인 모두 작동, 설치 가능

## 🏗️ 아키텍처

- **Frontend**: Vanilla JS + IndexedDB (오디오 로컬 저장)
- **Backend**: FastAPI + Edge TTS + asyncio 병렬 처리
- **Hosting**: Render.com 무료 플랜 (Docker)

## 📋 고도화 로드맵

### P0 (완료)
- ✅ 청크 단위 재시도 로직
- ✅ 음성 필터링 (tone/use_case)
- ✅ 클라이언트 기본 오디오북 자동 다운로드
- ✅ UX 개선 (토스트, 에러 메시지)

### P1 (향후)
- 배치 변환 (여러 문서 동시 업로드)
- Web Speech API 폴백
- 고급 플레이어 (속도, 반복)

### P2 (선택)
- 사용자 계정 & 클라우드 동기화
- 오디오북 메타 편집
- 수익화 (프리미엄 티어)
