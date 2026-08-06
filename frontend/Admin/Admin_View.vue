<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAdminState } from "./Admin_State.vue";
import { useAdminLogic } from "./Admin_Logic.vue";
import ThemeSheetView from "../Sheet/ThemeSheet_View.vue";
import { useThemeState } from "../Theme/Theme_State.vue";
import { useThemeLogic } from "../Theme/Theme_Logic.vue";

const {
    status, contentVisible, metrics, activeAdminTab, newsInputText, newsStatus, newsSubmitting,
    libraryInputText, libraryStatus, librarySubmitting,
    libraryItems, libraryItemsStatus, libraryTogglingIds, statusMenuItem, activeInputSheet,
} = useAdminState();
const {
    formatMetric, loadMetrics, selectTab, validateJson, submitNews, submitLibrary,
    loadLibraryItems, openStatusMenu, closeStatusMenu, toggleLibraryStatus,
    openInputSheet, closeInputSheet,
} = useAdminLogic({
    status, contentVisible, metrics, activeAdminTab, newsInputText, newsStatus, newsSubmitting,
    libraryInputText, libraryStatus, librarySubmitting,
    libraryItems, libraryItemsStatus, libraryTogglingIds, statusMenuItem, activeInputSheet,
});
const themeState = useThemeState();
const themeLogic = useThemeLogic(themeState);

const newsValidation = computed(() => validateJson(newsInputText.value));
const libraryValidation = computed(() => validateJson(libraryInputText.value));

function submitLabel(text: string, validation: { isValid: boolean; itemCount: number; errors: string[] }, submitting: boolean): string {
    if (submitting) return "등록 중...";
    if (!text.trim()) return "등록하기";
    if (validation.errors.length > 0) return "형식 확인 필요";
    return `${validation.itemCount}개 작품 등록`;
}
const newsSubmitLabel = computed(() => submitLabel(newsInputText.value, newsValidation.value, newsSubmitting.value));
const librarySubmitLabel = computed(() => submitLabel(libraryInputText.value, libraryValidation.value, librarySubmitting.value));
const newsCanSubmit = computed(() => !newsSubmitting.value && !!newsInputText.value.trim() && newsValidation.value.errors.length === 0);
const libraryCanSubmit = computed(() => !librarySubmitting.value && !!libraryInputText.value.trim() && libraryValidation.value.errors.length === 0);

// ⚠️ 임시 진단용. /admin?vpdebug 로 접속했을 때만 화면에 실측값을 띄운다.
// 실기기(iOS)에서만 재현되는 시트 하단 여백 문제의 원인을 좁히기 위한 것으로,
// 원인을 찾으면 이 블록은 통째로 제거한다.
const vpDebug = ref("");
// PWA(standalone)에서는 주소창이 없어 ?vpdebug를 붙일 수 없는데, 문제는
// 바로 그 PWA에서만 재현된다. 그래서 잠시 조건 없이 켜 둔다 — 관리자만
// 보는 화면이라 영향 범위가 좁다. 원인 확인 후 이 블록은 통째로 제거한다.
const showVpDebug = true;

function collectVpDebug(): void {
    const probe = document.createElement("div");
    probe.style.cssText = "position:fixed;bottom:0;height:env(safe-area-inset-bottom);width:1px;";
    document.body.appendChild(probe);
    const safeBottom = probe.getBoundingClientRect().height;
    probe.remove();

    const backdrop = document.querySelector(".action-sheet-backdrop.show");
    const card = backdrop?.querySelector(".action-sheet");
    const b = backdrop?.getBoundingClientRect();
    const c = card?.getBoundingClientRect();
    const vv = window.visualViewport;

    vpDebug.value = [
        `standalone=${(navigator as any).standalone} innerH=${window.innerHeight}`,
        `docClientH=${document.documentElement.clientHeight} screenH=${screen.height}`,
        `visualVP h=${vv?.height?.toFixed(1)} offTop=${vv?.offsetTop?.toFixed(1)} scale=${vv?.scale}`,
        `safeAreaBottom=${safeBottom}`,
        `backdrop top=${b?.top?.toFixed(1)} bottom=${b?.bottom?.toFixed(1)} h=${b?.height?.toFixed(1)}`,
        `card top=${c?.top?.toFixed(1)} bottom=${c?.bottom?.toFixed(1)} h=${c?.height?.toFixed(1)}`,
        `card gapFromScreenBottom=${c ? (window.innerHeight - c.bottom).toFixed(1) : "-"}`,
    ].join("\n");
}

onMounted(() => {
    loadMetrics();
    loadLibraryItems();
    if (showVpDebug) {
        setInterval(collectVpDebug, 500);
        window.visualViewport?.addEventListener("resize", collectVpDebug);
        window.visualViewport?.addEventListener("scroll", collectVpDebug);
    }
});
</script>

<template>
    <main class="dashboard-shell">
        <header class="dashboard-header">
            <div>
                <p class="eyebrow">TEXTAUDIO · PRODUCT PULSE</p>
                <h1>관리자</h1>
                <p class="dashboard-subtitle">개인 콘텐츠 없이 서비스 흐름만 집계합니다.</p>
            </div>
            <div class="header-actions">
                <a href="/" class="back-link">서비스로</a>
                <button type="button" @click="themeLogic.openSheet">화면 테마</button>
                <button type="button" @click="loadMetrics">새로고침</button>
            </div>
        </header>

        <p class="dashboard-status" role="status" aria-live="polite">{{ status }}</p>

        <nav class="admin-tabs" role="tablist" aria-label="관리자 화면 전환">
            <button type="button" class="admin-tab-btn" :class="{ active: activeAdminTab === 'dashboard' }" role="tab" :aria-selected="activeAdminTab === 'dashboard'" @click="selectTab('dashboard')">대시보드</button>
            <button type="button" class="admin-tab-btn" :class="{ active: activeAdminTab === 'create' }" role="tab" :aria-selected="activeAdminTab === 'create'" @click="selectTab('create')">콘텐츠 등록</button>
            <button type="button" class="admin-tab-btn" :class="{ active: activeAdminTab === 'publishing' }" role="tab" :aria-selected="activeAdminTab === 'publishing'" @click="selectTab('publishing')">발행 관리</button>
        </nav>

        <section v-show="contentVisible">
            <section v-show="activeAdminTab === 'dashboard'" class="metric-section" aria-labelledby="retentionHeading">
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

            <section v-show="activeAdminTab === 'create'" class="metric-section" aria-labelledby="createHeading">
                <div class="section-heading">
                    <p class="section-kicker">CONTENT</p>
                    <h2 id="createHeading">콘텐츠 등록</h2>
                </div>
                <ul class="content-create-list">
                    <li class="content-create-row" @click="openInputSheet('news')">
                        <div>
                            <strong>경제 뉴스 추가</strong>
                            <span>JSON 배열로 뉴스를 등록합니다</span>
                        </div>
                        <span class="content-create-chevron">›</span>
                    </li>
                    <li class="content-create-row" @click="openInputSheet('library')">
                        <div>
                            <strong>라이브러리 작품 추가</strong>
                            <span>JSON 배열로 경전·철학·고전 작품을 등록합니다</span>
                        </div>
                        <span class="content-create-chevron">›</span>
                    </li>
                </ul>
            </section>

            <section v-show="activeAdminTab === 'publishing'" class="metric-section" aria-labelledby="libraryReviewHeading">
                <div class="section-heading">
                    <p class="section-kicker">LIBRARY · 검토 및 발행</p>
                    <h2 id="libraryReviewHeading">등록된 작품 관리</h2>
                </div>
                <p class="dashboard-subtitle" v-if="libraryItemsStatus">{{ libraryItemsStatus }}</p>
                <ul class="library-review-list" v-if="libraryItems.length">
                    <li v-for="item in libraryItems" :key="item.id" class="library-review-row">
                        <div class="library-review-info">
                            <strong>{{ item.title }}</strong>
                            <span>
                                <template v-if="item.library_category">{{ item.library_category }} · </template>{{ item.library_description || "설명 없음" }}
                            </span>
                        </div>
                        <div class="library-review-actions">
                            <span class="library-status-badge" :class="`is-${item.library_status}`">
                                {{ item.library_status === "published" ? "공개" : "검토중" }}
                            </span>
                            <button
                                type="button"
                                class="row-more-btn"
                                aria-label="더보기"
                                :disabled="libraryTogglingIds.has(item.id)"
                                @click="openStatusMenu(item)"
                            >⋯</button>
                        </div>
                    </li>
                </ul>
                <p class="dashboard-subtitle" v-else-if="!libraryItemsStatus">등록된 작품이 없습니다.</p>
            </section>
        </section>
    </main>

    <ThemeSheetView :state="themeState" :logic="themeLogic" />

    <div class="action-sheet-backdrop" :class="{ show: !!statusMenuItem }" role="dialog" aria-modal="true" @click="(e) => { if (e.target === e.currentTarget) closeStatusMenu(); }">
        <div class="action-sheet" v-if="statusMenuItem">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header"><h3>{{ statusMenuItem.title }}</h3></div>
            <button type="button" class="action-sheet-btn" @click="toggleLibraryStatus(statusMenuItem)">
                {{ statusMenuItem.library_status === "published" ? "비공개로 전환" : "공개로 전환" }}
            </button>
            <button type="button" class="action-sheet-btn action-sheet-btn-cancel" @click="closeStatusMenu">취소</button>
        </div>
    </div>

    <div class="action-sheet-backdrop" :class="{ show: activeInputSheet === 'news' }" role="dialog" aria-modal="true" @click="(e) => { if (e.target === e.currentTarget) closeInputSheet(); }">
        <div class="action-sheet input-sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header"><h3>경제 뉴스 추가</h3></div>
            <div class="input-sheet-scroll">
                <p class="dashboard-subtitle">아래 형식에 맞는 json을 붙여넣으세요.</p>
                <textarea
                    class="news-input"
                    rows="10"
                    placeholder='[
  {
    "title": "뉴스 제목",
    "content": "요약 본문",
    "category": "국제",
    "source": "Reuters"
  }
]'
                    v-model="newsInputText"
                ></textarea>
                <ul class="json-errors" v-if="newsValidation.errors.length">
                    <li v-for="(error, i) in newsValidation.errors" :key="i">{{ error }}</li>
                </ul>
                <div class="json-preview" v-else-if="newsValidation.itemCount > 0">
                    <p>{{ newsValidation.itemCount }}개 항목 인식됨</p>
                    <ul>
                        <li v-for="(title, i) in newsValidation.previewTitles" :key="i">{{ title }}</li>
                    </ul>
                </div>
            </div>
            <div class="news-input-actions">
                <button type="button" :disabled="!newsCanSubmit" @click="submitNews">{{ newsSubmitLabel }}</button>
                <span class="news-status">{{ newsStatus }}</span>
            </div>
            <button type="button" class="action-sheet-btn action-sheet-btn-cancel" @click="closeInputSheet">닫기</button>
        </div>
    </div>

    <div class="action-sheet-backdrop" :class="{ show: activeInputSheet === 'library' }" role="dialog" aria-modal="true" @click="(e) => { if (e.target === e.currentTarget) closeInputSheet(); }">
        <div class="action-sheet input-sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header"><h3>라이브러리 작품 추가</h3></div>
            <div class="input-sheet-scroll">
                <p class="dashboard-subtitle">아래 형식에 맞는 json을 붙여넣으세요.</p>
                <textarea
                    class="news-input"
                    rows="10"
                    placeholder='[
  {
    "title": "도덕경",
    "category": "철학·사상",
    "edition": "왕필본",
    "translator": "원문 기반",
    "source": "중국 고전 《도덕경》",
    "rights": "원전 공개 이용 가능",
    "description": "노자가 전하는 도와 덕의 철학...",
    "status": "published",
    "content": "# 1장\n도가도 비상도...\n\n# 2장\n..."
  }
]'
                    v-model="libraryInputText"
                ></textarea>
                <ul class="json-errors" v-if="libraryValidation.errors.length">
                    <li v-for="(error, i) in libraryValidation.errors" :key="i">{{ error }}</li>
                </ul>
                <div class="json-preview" v-else-if="libraryValidation.itemCount > 0">
                    <p>{{ libraryValidation.itemCount }}개 항목 인식됨</p>
                    <ul>
                        <li v-for="(title, i) in libraryValidation.previewTitles" :key="i">{{ title }}</li>
                    </ul>
                </div>
            </div>
            <div class="news-input-actions">
                <button type="button" :disabled="!libraryCanSubmit" @click="submitLibrary">{{ librarySubmitLabel }}</button>
                <span class="news-status">{{ libraryStatus }}</span>
            </div>
            <button type="button" class="action-sheet-btn action-sheet-btn-cancel" @click="closeInputSheet">닫기</button>
        </div>
    </div>

    <!-- ⚠️ 임시 진단 오버레이 (/admin?vpdebug). 원인 확인 후 제거한다. -->
    <pre
        v-if="showVpDebug"
        style="position:fixed;top:0;left:0;right:0;z-index:9999;margin:0;padding:6px 8px;
               background:rgba(0,0,0,0.85);color:#0f0;font:600 10px/1.35 ui-monospace,monospace;
               white-space:pre-wrap;pointer-events:none;"
    >{{ vpDebug }}</pre>
</template>
