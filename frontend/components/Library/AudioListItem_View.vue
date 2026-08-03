<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import type { AudioListLogic } from "./AudioList_Logic.vue";
import { getAudiobookDisplayTitle } from "../../utils/format";

const props = withDefaults(defineProps<{
    audio: AudiobookRecord;
    logic: AudioListLogic;
    swipeEnabled?: boolean;
}>(), {
    swipeEnabled: true,
});

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
    if (isSwipeOpen.value && front.value && !front.value.contains(event.target as Node)) resetTransform();
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
    <div class="audio-item" :class="{ 'deleting-row': isDeleting, 'swipe-open': isSwipeOpen }" @click="onItemClick">
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
                <i data-lucide="play-circle"></i>
                <span class="audio-title" :title="getAudiobookDisplayTitle(audio.title)">{{ getAudiobookDisplayTitle(audio.title) }}</span>
                <span v-if="audio.isDefault" class="default-badge" title="기본 제공 오디오북">기본 제공</span>
                <svg v-if="audio.isBookmarked" class="bookmark-star" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="none" title="즐겨찾기"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </div>
            <div class="audio-actions">
                <button class="btn-icon-round btn-more" title="더보기" @click.stop="logic.openActionSheet(audio)">
                    <i data-lucide="more-horizontal"></i>
                </button>
            </div>
        </div>
    </div>
</template>
