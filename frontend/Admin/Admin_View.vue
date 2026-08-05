<script setup lang="ts">
import { onMounted } from "vue";
import { useAdminState } from "./Admin_State.vue";
import { useAdminLogic } from "./Admin_Logic.vue";
import ThemeSheetView from "../Sheet/ThemeSheet_View.vue";
import { useThemeState } from "../Theme/Theme_State.vue";
import { useThemeLogic } from "../Theme/Theme_Logic.vue";

const {
    status, contentVisible, metrics, newsInputText, newsStatus, newsSubmitting,
    libraryInputText, libraryStatus, librarySubmitting,
} = useAdminState();
const { formatMetric, loadMetrics, submitNews, submitLibrary } = useAdminLogic({
    status, contentVisible, metrics, newsInputText, newsStatus, newsSubmitting,
    libraryInputText, libraryStatus, librarySubmitting,
});
const themeState = useThemeState();
const themeLogic = useThemeLogic(themeState);

onMounted(loadMetrics);
</script>

<template>
    <main class="dashboard-shell">
        <header class="dashboard-header">
            <div>
                <p class="eyebrow">TEXTAUDIO · PRODUCT PULSE</p>
                <h1>이용 현황</h1>
                <p class="dashboard-subtitle">개인 콘텐츠 없이 서비스 흐름만 집계합니다.</p>
            </div>
            <div class="header-actions">
                <a href="/" class="back-link">서비스로</a>
                <button type="button" @click="themeLogic.openSheet">화면 테마</button>
                <button type="button" @click="loadMetrics">새로고침</button>
            </div>
        </header>

        <p class="dashboard-status" role="status" aria-live="polite">{{ status }}</p>

        <section v-show="contentVisible">
            <section class="metric-section" aria-labelledby="retentionHeading">
                <div class="section-heading">
                    <p class="section-kicker">READER HABIT</p>
                    <h2 id="retentionHeading">다시 듣는가</h2>
                </div>
                <div class="metric-grid">
                    <a class="metric-card metric-card-primary" href="/admin/metrics/weekly_active_users">
                        <p>주간 활성 사용자</p>
                        <strong data-metric="weekly_active_users">{{ formatMetric('weekly_active_users', metrics.weekly_active_users) }}</strong>
                        <span>최근 7일 이벤트 기준</span>
                    </a>
                    <a class="metric-card" href="/admin/metrics/daily_active_users">
                        <p>일간 활성 사용자</p>
                        <strong data-metric="daily_active_users">{{ formatMetric('daily_active_users', metrics.daily_active_users) }}</strong>
                        <span>최근 24시간 이벤트 기준</span>
                    </a>
                    <a class="metric-card" href="/admin/metrics/week_one_retention_rate">
                        <p>1주 재방문율</p>
                        <strong data-metric="week_one_retention_rate">{{ formatMetric('week_one_retention_rate', metrics.week_one_retention_rate) }}</strong>
                        <span>{{ metrics.retention_cohort_size ? `${metrics.retention_cohort_size}명 코호트 기준` : "측정 코호트 없음" }}</span>
                    </a>
                </div>
            </section>

            <section class="metric-section" aria-labelledby="funnelHeading">
                <div class="section-heading">
                    <p class="section-kicker">CORE LOOP</p>
                    <h2 id="funnelHeading">만들고 듣는가</h2>
                </div>
                <div class="metric-grid metric-grid-wide">
                    <a class="metric-card" href="/admin/metrics/total_users">
                        <p>전체 사용자</p>
                        <strong data-metric="total_users">{{ formatMetric('total_users', metrics.total_users) }}</strong>
                        <span><b>{{ formatMetric('new_users_7d', metrics.new_users_7d) }}</b>명 · 최근 7일 가입</span>
                    </a>
                    <a class="metric-card" href="/admin/metrics/generation_success_rate">
                        <p>생성 성공률</p>
                        <strong data-metric="generation_success_rate">{{ formatMetric('generation_success_rate', metrics.generation_success_rate) }}</strong>
                        <span><b>{{ formatMetric('generation_completed_30d', metrics.generation_completed_30d) }}</b>건 완료 · 최근 30일</span>
                    </a>
                    <a class="metric-card" href="/admin/metrics/playback_started_30d">
                        <p>첫 재생</p>
                        <strong data-metric="playback_started_30d">{{ formatMetric('playback_started_30d', metrics.playback_started_30d) }}</strong>
                        <span>최근 30일 시작 횟수</span>
                    </a>
                    <a class="metric-card" href="/admin/metrics/total_audiobooks">
                        <p>보관함 오디오북</p>
                        <strong data-metric="total_audiobooks">{{ formatMetric('total_audiobooks', metrics.total_audiobooks) }}</strong>
                        <span><b>{{ formatMetric('generation_failed_30d', metrics.generation_failed_30d) }}</b>건 · 최근 30일 실패</span>
                    </a>
                </div>
            </section>

            <section class="metric-section" aria-labelledby="newsHeading">
                <div class="section-heading">
                    <p class="section-kicker">HOME · ECONOMIC NEWS</p>
                    <h2 id="newsHeading">경제 뉴스 추가</h2>
                </div>
                <p class="dashboard-subtitle">
                    [{"title": "...", "content": "...", "category": "...", "source": "..."}] 형식의 JSON 배열을 붙여넣으세요.
                </p>
                <textarea
                    class="news-input"
                    rows="10"
                    placeholder='[{"title": "뉴스 제목", "content": "요약 본문", "category": "국제", "source": "Reuters"}]'
                    v-model="newsInputText"
                ></textarea>
                <div class="news-input-actions">
                    <button type="button" :disabled="newsSubmitting" @click="submitNews">
                        {{ newsSubmitting ? "등록 중..." : "등록하기" }}
                    </button>
                    <span class="news-status">{{ newsStatus }}</span>
                </div>
            </section>

            <section class="metric-section" aria-labelledby="libraryHeading">
                <div class="section-heading">
                    <p class="section-kicker">LIBRARY · 경전·철학·고전</p>
                    <h2 id="libraryHeading">라이브러리 작품 추가</h2>
                </div>
                <p class="dashboard-subtitle">
                    작품 배열을 JSON으로 붙여넣으세요. 필드: title(필수) · content(필수, 마크다운 —
                    "# 장 제목"으로 챕터를 나누면 목차가 자동 생성됨) · category ·
                    edition(판본) · translator(번역/편저) · source(출처) ·
                    rights(이용 조건, 자유 텍스트) · description(1~2문장 소개) ·
                    status("published"로 명시해야 공개됨, 생략 시 "review"로 비공개 저장).
                </p>
                <textarea
                    class="news-input"
                    rows="10"
                    placeholder='[{"title": "도덕경", "category": "철학·사상", "edition": "왕필본", "translator": "원문 기반", "source": "중국 고전 《도덕경》", "rights": "원전 공개 이용 가능", "description": "노자가 전하는 도와 덕의 철학...", "status": "published", "content": "# 1장\n도가도 비상도...\n\n# 2장\n..."}]'
                    v-model="libraryInputText"
                ></textarea>
                <div class="news-input-actions">
                    <button type="button" :disabled="librarySubmitting" @click="submitLibrary">
                        {{ librarySubmitting ? "등록 중..." : "등록하기" }}
                    </button>
                    <span class="news-status">{{ libraryStatus }}</span>
                </div>
            </section>
        </section>
    </main>

    <ThemeSheetView :state="themeState" :logic="themeLogic" />
</template>
