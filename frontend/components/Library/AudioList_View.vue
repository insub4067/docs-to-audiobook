<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { AudioListState } from "./AudioList_State.vue";
import type { AudioListLogic } from "./AudioList_Logic.vue";
import type { GeneratingItem } from "../../composables/Generation/Generation_State.vue";
import AudioListItemView from "./AudioListItem_View.vue";
import ActionSheetView from "./ActionSheet_View.vue";

const props = defineProps<{
    state: AudioListState;
    logic: AudioListLogic;
    generatingItems: GeneratingItem[];
    onImportLink: () => void;
}>();

const isEmpty = computed(() =>
    props.generatingItems.length === 0
    && props.state.backgroundJobItems.value.length === 0
    && props.state.savedAudiobooks.value.length === 0
);

onMounted(() => props.logic.load());
</script>

<template>
    <section class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="folder-heart" class="header-icon"></i>
            <h2>내 오디오북</h2>
            <button
                class="btn-icon"
                aria-label="공유 링크 불러오기"
                title="공유 링크 불러오기"
                style="margin-left: auto; width: 44px; height: 44px; border-radius: 50%; background: var(--glass-bg); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-color); transition: all 0.3s ease;"
                @click="onImportLink"
            >
                <i data-lucide="link" style="width: 18px; height: 18px;"></i>
            </button>
        </div>

        <div class="library-container">
            <div class="library-empty" v-show="isEmpty">
                <i data-lucide="music"></i>
                <p>아직 생성된 책이 없습니다.</p>
                <span>새로운 문서를 업로드해 보세요.</span>
            </div>

            <div class="audio-list">
                <div v-for="item in generatingItems" :key="item.id" class="audio-item audio-item-generating">
                    <div class="audio-title-group">
                        <div class="generating-spinner"></div>
                        <div class="generating-info">
                            <span class="audio-title">{{ item.title }}</span>
                            <div class="generating-progress-track">
                                <div class="generating-progress-fill" :style="{ width: item.progressPercent + '%' }"></div>
                            </div>
                            <span class="generating-status">{{ item.statusText }}</span>
                        </div>
                    </div>
                </div>

                <div v-for="item in state.backgroundJobItems.value" :key="item.jobId" class="audio-item audio-item-generating">
                    <div class="audio-title-group">
                        <div class="generating-spinner"></div>
                        <div class="generating-info">
                            <span class="audio-title">{{ item.title }}</span>
                            <span class="generating-status">서버에서 생성 중...</span>
                        </div>
                    </div>
                </div>

                <AudioListItemView v-for="audio in state.savedAudiobooks.value" :key="audio.id" :audio="audio" :logic="logic" />
            </div>
        </div>
    </section>

    <ActionSheetView :state="state" :logic="logic" />
</template>
