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

### 📄 문서 처리
- **형식 지원**: DOCX, PDF, TXT, MD, HWP
- **배치 변환**: 여러 문서 동시 업로드 & 순차 처리
- **음성 선택**: 7개 한국어 음성 + 톤/용도별 필터링

### 🎵 플레이어 기능
- **고급 컨트롤**: 시간 건너뛰기 (±10초), 재생 속도 (0.75x~2.0x)
- **반복 모드**: 반복 안 함 / 전체 반복 / 한 곡 반복
- **취침 타이머**: 15/30/60분 자동 정지

### 🔧 신뢰성
- **재시도 로직**: 청크 단위 재시도로 Edge-TTS 간헐적 오류 극복
- **폴백 시스템**: Web Speech API로 자동 전환
- **오프라인 재생**: IndexedDB 로컬 저장

### 🎁 기본 제공
- **샘플 오디오북**: 셜록 홈즈의 모험 자동 다운로드
- **PWA 지원**: 온/오프라인 작동, 설치 가능

## 🏗️ 아키텍처

- **Frontend**: Vanilla JS + IndexedDB (오디오 로컬 저장)
- **Backend**: FastAPI + Edge TTS + asyncio 병렬 처리
- **Hosting**: Render.com 무료 플랜 (Docker)

## 📋 개발 현황

### ✅ P0 (완료)
- 문서 변환 (DOCX, PDF, TXT, MD, HWP)
- 청크 단위 재시도 로직
- 음성 필터링 (tone/use_case)
- 기본 오디오북 자동 다운로드
- 모달/스크롤 UX 개선

### ✅ P1 (완료)
- ✅ 고급 플레이어 (시간 건너뛰기, 반복 모드)
- ✅ Web Speech API 폴백
- ✅ 배치 변환 (다중 파일 업로드)

### 📋 P2 (계획 중)
- 사용자 계정 시스템
- Supabase 연동 (DB + Auth + Storage)
- 오디오북 클라우드 동기화
- 다기기 재생 상태 동기화

### 🚀 P3 (향후)
- 오디오북 메타 편집
- 공유 & 협업
- 수익화 (프리미엄 기능)
