---
title: Docs To Audiobook
emoji: 🎧
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
---

# Docs to Audiobook Converter

FastAPI + Vanilla JS Audiobook generator utilizing Edge TTS, supporting smart text chunking, voice filtering, client-side IndexedDB persistent storage, and Supabase cloud synchronization.

## 🚀 Features

### 📄 문서 처리
- **형식 지원**: DOCX, PDF, TXT, MD, HWP
- **배치 변환**: 여러 문서 동시 업로드 & 순차 병렬 처리
- **음성 선택**: 7개 한국어 음성 + 톤/용도별 필터링
- **스마트 텍스트 처리**: HWP/Markdown 목차(Heading) 추출, 문장 단위 동기화 및 TTS용 특수문자 전처리

### 🎵 플레이어 기능
- **고급 컨트롤**: 시간 건너뛰기 (±10초), 재생 속도 (0.75x~2.0x)
- **반복 모드**: 반복 안 함 / 전체 반복 / 한 곡 반복
- **취침 타이머**: 15/30/60분 자동 정지

### 🔧 신뢰성 & 성능
- **재시도 로직**: 청크 단위 재시도로 Edge-TTS 간헐적 오류 극복
- **폴백 시스템**: Web Speech API로 자동 전환
- **테스트 커버리지**: 100% 테스트 자동화 (pytest) 및 GitHub Actions CI/CD 파이프라인

### 🎨 UI/UX 고도화
- **사용성 개선**: 모바일 환경에 최적화된 스와이프 제스처 및 액션 모달
- **새로고침 UX**: iOS 스타일의 12-Spokes 당겨서 새로고침(Pull-to-refresh) 지원
- **오프라인/PWA**: 로컬 IndexedDB 저장, 온/오프라인 작동 및 앱 설치 가능

### ☁️ 클라우드 및 소셜 기능
- **계정 및 동기화**: Google/Kakao 소셜 로그인 및 사용자 기기 간 오디오북 클라우드 동기화 (Supabase)
- **공유 기능**: 고유 웹 링크를 통한 생성된 오디오북 공유 기능 지원

## 🏗️ 아키텍처

- **Frontend**: Vanilla JS + IndexedDB (로컬 캐싱) + PWA
- **Backend**: FastAPI + Edge TTS + asyncio 병렬 처리
- **Cloud/DB**: Supabase (PostgreSQL, Auth Token, Meta Storage)
- **Hosting**: Fly.io (Docker 배포)
- **CI/CD**: GitHub Actions (병렬 테스트 및 자동 배포)

## 📋 개발 현황

### ✅ P0 & P1 (코어 기능 완료)
- 문서 변환 (DOCX, PDF, TXT, MD, HWP)
- 청크 단위 재시도 로직 및 Web Speech API 폴백
- 음성 필터링 (tone/use_case) 및 다중 파일 업로드 처리
- 고급 플레이어 (시간 건너뛰기, 반복 모드)

### ✅ P2 (클라우드 연동 완료)
- 사용자 계정 시스템 (Google, Kakao OAuth)
- Supabase 기반 메타데이터 동기화 (DB + Auth)
- 오디오북 클라우드 데이터 백그라운드 동기화

### 🚀 P3 (진행 중 / 향후 계획)
- ✅ 오디오북 고유 링크 공유 기능 (완료)
- 다기기 재생 상태(Playback History) 실시간 동기화
- 오디오북 메타데이터 편집
- 수익화 및 프론트엔드 프레임워크 고도화
