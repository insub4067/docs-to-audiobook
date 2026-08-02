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
}>();

const isEmpty = computed(() => props.generatingItems.length === 0 && props.state.savedAudiobooks.value.length === 0);

onMounted(() => props.logic.load());
</script>

<template>
    <section class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="folder-heart" class="header-icon"></i>
            <h2>내 오디오북</h2>
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

                <AudioListItemView v-for="audio in state.savedAudiobooks.value" :key="audio.id" :audio="audio" :logic="logic" />
            </div>
        </div>
    </section>

    <ActionSheetView :state="state" :logic="logic" />
</template>
