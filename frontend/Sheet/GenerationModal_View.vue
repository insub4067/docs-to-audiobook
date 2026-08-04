<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAuthStore } from "../stores/auth";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import type { VoiceState } from "../Voices/Voice_State.vue";
import type { VoiceLogic } from "../Voices/Voice_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    voiceState: VoiceState;
    voiceLogic: VoiceLogic;
}>();

const authStore = useAuthStore();
const modalContent = ref<HTMLElement | null>(null);

// state.py의 MAX_SYNTH_CHARS와 같은 값 — 관리자는 사실상 무제한(5천만 자)이라
// 굳이 분모로 보여줄 필요가 없다.
const MAX_SYNTH_CHARS = 100_000;
const charBadgeLabel = computed(() => {
    const count = props.state.charCount.value.toLocaleString();
    if (authStore.isAdmin) return `${count}자`;
    return `${count} / ${MAX_SYNTH_CHARS.toLocaleString()}자`;
});

useSwipeToDismiss(modalContent, () => props.logic.closeModal());

watch(() => props.state.isModalOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onVoiceChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    props.voiceLogic.updateDescription(value);
    props.voiceLogic.stopPreview();
}
</script>

<template>
    <div class="generation-modal" :class="{ show: state.isModalOpen.value }" role="dialog" aria-modal="true" aria-labelledby="generationTitle">
        <div class="modal-content glass-card" ref="modalContent">
            <header class="modal-header">
                <h2 id="generationTitle">오디오북 설정 및 미리보기</h2>
                <button class="btn-icon" aria-label="닫기" title="닫기" @click="logic.closeModal">
                    <i data-lucide="x"></i>
                </button>
            </header>

            <div class="modal-scroll-area">
                <div class="modal-section">
                    <div class="section-title">
                        <i data-lucide="eye" class="header-icon"></i> 텍스트 확인
                        <span class="char-badge" v-show="state.isCharBadgeVisible.value">{{ charBadgeLabel }}</span>
                    </div>
                    <div class="preview-text" v-show="state.isPreviewVisible.value">{{ state.previewText.value }}</div>
                </div>

                <div class="modal-section">
                    <div class="section-title">
                        <i data-lucide="sliders" class="header-icon"></i> 음성 설정
                    </div>
                    <div class="settings-form">
                        <div class="form-group">
                            <label for="voiceSelect">낭독자 목소리</label>
                            <div class="voice-row">
                                <div class="select-wrapper">
                                    <select id="voiceSelect" v-model="voiceState.selectedVoice.value" @change="onVoiceChange">
                                        <option v-if="voiceState.voices.value.length === 0" value="" disabled selected>불러오는 중...</option>
                                        <option v-for="voice in voiceState.voices.value" :key="voice.key" :value="voice.key">
                                            {{ voice.friendly_name }}
                                        </option>
                                    </select>
                                    <i data-lucide="chevron-down" class="select-arrow"></i>
                                </div>
                                <button type="button" class="btn-voice-preview" aria-label="선택한 목소리 미리듣기" title="선택한 목소리 미리듣기" @click="voiceLogic.togglePreview">
                                    <i data-lucide="volume-2"></i>
                                    <span>{{ voiceState.previewLabel.value }}</span>
                                </button>
                            </div>
                            <div class="voice-desc">{{ voiceState.voiceDesc.value }}</div>
                        </div>
                        <div class="form-group">
                            <div class="label-with-val">
                                <label for="speedSlider">읽기 속도</label>
                                <span class="slider-val">{{ logic.formattedSpeedLabel(state.speed.value) }}</span>
                            </div>
                            <input type="range" id="speedSlider" min="-50" max="100" step="5" v-model.number="state.speed.value">
                        </div>
                        <div class="form-group">
                            <div class="label-with-val">
                                <label for="pitchSlider">목소리 높낮이</label>
                                <span class="slider-val">{{ logic.formattedPitchLabel(state.pitch.value) }}</span>
                            </div>
                            <input type="range" id="pitchSlider" min="-50" max="50" step="2" v-model.number="state.pitch.value">
                        </div>
                    </div>
                </div>
            </div>

            <div class="modal-footer">
                <p class="generate-hint" v-if="!authStore.isLoggedIn">로그인 없이 오디오북 한 권을 만들어 볼 수 있어요</p>
                <button class="btn btn-primary btn-generate" @click="logic.onGenerateClick">
                    <i data-lucide="sparkles"></i>
                    <span>오디오북 만들기</span>
                </button>
            </div>
        </div>
    </div>
</template>
