<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import type { AudioListLogic } from "./AudioList_Logic.vue";
import { getAudiobookDisplayTitle } from "../../utils/format";
import { nowPlayingId, nowPlayingState } from "../../services/nowPlaying";

const props = withDefaults(defineProps<{
    audio: AudiobookRecord;
    logic: AudioListLogic;
    swipeEnabled?: boolean;
}>(), {
    swipeEnabled: true,
});

// 지금 듣고 있는 항목은 목록에서 바로 알아볼 수 있어야 한다. 재생목록
// 시트와 같은 표시를 쓴다 — 화면마다 신호가 다르면 매번 새로 배워야 한다.
// "지금 듣는 것"과 "듣다 멈춘 것"을 나눈다. 행 강조는 둘 다에 걸고,
// 움직이는 막대는 실제로 소리가 날 때만 보여준다.
const isCurrent = computed(() => nowPlayingId.value === props.audio.id);
const isPlaying = computed(() => isCurrent.value && nowPlayingState.value === "playing");

const root = ref<HTMLElement | null>(null);
const front = ref<HTMLElement | null>(null);
const isSwipeOpen = ref(false);
const isDeleting = ref(false);
const isDragging_ = ref(false);

let startX = 0;
let startY = 0;
let currentX = 0;
let isDragging = false;
let isSwipe = false;

const hasSentences = !!(props.audio.sentences && props.audio.sentences.length > 0);
const needsDownload = !props.audio.audioData && !!props.audio.audioUrl;
const isOpenable = hasSentences || needsDownload;

// 한 번이라도 열어 본 오디오북은 리더가 총 길이를 저장해 둔다. 그 전에는
// 진행률을 계산할 수 없으므로(길이를 알려면 오디오를 디코딩해야 한다)
// 아무것도 보여주지 않는다 — 서점 카드와 같은 규칙이다.
const FINISHED_RATIO = 0.97;

const progress = computed(() => {
    const seconds = props.audio.lastPosition;
    const total = props.audio.durationSeconds;
    if (!seconds || !total) return null;

    const ratio = Math.min(seconds / total, 1);
    const remainingMinutes = Math.round((total - seconds) / 60);
    return {
        percent: Math.round(ratio * 100),
        isFinished: ratio >= FINISHED_RATIO,
        remainingLabel: remainingMinutes > 0 ? `약 ${remainingMinutes}분 남음` : "1분 미만 남음",
    };
});

// 목록에서 파일을 구분하기 쉽도록 생성 날짜를 짧게 보여준다.
const subtitleLabel = computed(() => {
    if (!props.audio.timestamp) return "";
    const date = new Date(props.audio.timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    if (isToday) return "오늘 생성";
    return `${date.getMonth() + 1}월 ${date.getDate()}일 생성`;
});

function resetTransform(): void {
    if (front.value) front.value.style.transform = "";
    isSwipeOpen.value = false;
}

function onTouchStart(event: TouchEvent): void {
    if (!props.swipeEnabled) return;
    startX = event.touches[0].clientX;
    startY = event.touches[0].clientY;
    currentX = startX;
    isDragging = true;
    isSwipe = false;
    isDragging_.value = true;
}

function onTouchMove(event: TouchEvent): void {
    if (!isDragging || !front.value) return;
    const x = event.touches[0].clientX;
    const y = event.touches[0].clientY;
    const deltaX = x - startX;
    const deltaY = y - startY;
    if (!isSwipe) {
        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 5) isSwipe = true;
        else if (Math.abs(deltaY) > 5) {
            isDragging = false;
            isDragging_.value = false;
            return;
        }
    }
    if (!isSwipe) return;
    if (event.cancelable) event.preventDefault();
    currentX = x;
    if (deltaX < 0) front.value.style.transform = `translateX(${deltaX}px)`;
    else if (deltaX > 0) front.value.style.transform = `translateX(${deltaX * 0.15}px)`;
}

function onTouchEnd(): void {
    if (!isDragging || !front.value) return;
    isDragging = false;
    isDragging_.value = false;
    const deltaX = currentX - startX;
    if (deltaX < -150) {
        if (navigator.vibrate) navigator.vibrate(50);
        if (window.confirm("정말 이 오디오북을 삭제하시겠습니까?")) {
            isDeleting.value = true;
            setTimeout(() => props.logic.deleteAudiobook(props.audio.id), 350);
        } else {
            resetTransform();
        }
    } else if (deltaX < -40) {
        front.value.style.transform = "translateX(-80px)";
        isSwipeOpen.value = true;
    } else {
        resetTransform();
    }
}

function onBgClick(event: MouseEvent): void {
    event.stopPropagation();
    if (window.confirm("정말 이 오디오북을 삭제하시겠습니까?")) props.logic.deleteAudiobook(props.audio.id);
}

function onDocumentTouchStart(event: TouchEvent): void {
    // front(앞면)만 기준으로 삼으면 안 된다 — 스와이프로 드러난 빨간
    // 삭제 배경(.audio-item-bg)은 front의 형제 요소라 거기를 눌러도
    // "바깥을 눌렀다"고 오판해 즉시 닫혀 버린다. 그러면 같은 터치의
    // click은 이미 원위치로 돌아온 front에서 발생하고, isSwipeOpen이
    // 먼저 꺼진 탓에 onItemClick의 방어 로직도 못 걸려 읽기모드가
    // 열리는 버그로 이어진다 — 반드시 행 전체(root) 기준으로 판단한다.
    if (isSwipeOpen.value && root.value && !root.value.contains(event.target as Node)) resetTransform();
}

async function onItemClick(event: MouseEvent): Promise<void> {
    if (isSwipeOpen.value) {
        resetTransform();
        return;
    }
    if ((event.target as HTMLElement).closest(".btn-more")) return;
    if (!isOpenable) return;
    await props.logic.openItem(props.audio);
}

onMounted(() => document.addEventListener("touchstart", onDocumentTouchStart, { passive: true }));
onUnmounted(() => document.removeEventListener("touchstart", onDocumentTouchStart));
</script>

<template>
    <div
        ref="root"
        class="audio-item"
        :class="{ 'deleting-row': isDeleting, 'swipe-open': isSwipeOpen, 'is-playing': isCurrent, 'is-paused': isCurrent && !isPlaying }"
        :aria-current="isCurrent ? 'true' : undefined"
        @click="onItemClick"
    >
        <div class="audio-item-bg" @click="onBgClick"><i data-lucide="trash-2"></i></div>
        <div
            ref="front"
            class="audio-item-front"
            :class="{ 'ui-dragging': isDragging_, deleting: isDeleting }"
            @touchstart.passive="onTouchStart"
            @touchmove="onTouchMove"
            @touchend.passive="onTouchEnd"
        >
            <div class="audio-title-group">
                <span class="row-play-icon">
                    <i data-lucide="play-circle"></i>
                    <span class="row-play-bars" aria-hidden="true"><span></span><span></span><span></span></span>
                </span>
                <div class="audio-title-col">
                    <span class="audio-title" :title="getAudiobookDisplayTitle(audio.title)">{{ getAudiobookDisplayTitle(audio.title) }}</span>
                    <span v-if="subtitleLabel" class="audio-subtitle">{{ subtitleLabel }}</span>

                    <!-- 행을 누르면 마지막 위치에서 이어지므로 별도 버튼은 두지 않는다. -->
                    <template v-if="progress">
                        <span v-if="progress.isFinished" class="library-progress-done">모두 들음</span>
                        <div v-else class="library-progress">
                            <div class="library-progress-track">
                                <div class="library-progress-fill" :style="{ width: progress.percent + '%' }"></div>
                            </div>
                            <span class="audio-subtitle">{{ progress.percent }}% · {{ progress.remainingLabel }}</span>
                        </div>
                    </template>
                </div>
                <span v-if="audio.isDefault" class="default-badge" title="기본 제공 오디오북">기본 제공</span>
                <svg v-if="audio.isBookmarked" class="bookmark-star" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="none" title="즐겨찾기"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </div>
            <div class="audio-actions">
                <button class="btn-icon-round btn-more" aria-label="더보기" @click.stop="logic.openActionSheet(audio)">
                    <i data-lucide="more-horizontal"></i>
                </button>
            </div>
        </div>
    </div>
</template>
