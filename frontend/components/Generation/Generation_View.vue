<script setup lang="ts">
import { useGenerationState } from './Generation_State.vue';
import { useGenerationLogic } from './Generation_Logic.vue';
import { useAuthStore } from '../../stores/auth';

const state = useGenerationState();
const logic = useGenerationLogic(state);
const authStore = useAuthStore();
</script>

<template>
  <div class="modal-scroll-area" v-if="!state.isGenerating.value">
    <!-- Text Preview -->
    <div class="modal-section">
      <div class="section-title">
        <i data-lucide="eye" class="header-icon"></i> 텍스트 확인
        <span class="char-badge">{{ state.charCount.value }} 자</span>
      </div>
      <div class="preview-text">
        {{ state.previewText.value }}
      </div>
    </div>

    <!-- Voice Settings -->
    <div class="modal-section">
      <div class="section-title">
        <i data-lucide="sliders" class="header-icon"></i> 음성 설정
      </div>
      <div class="settings-form">
        <!-- Voice Selector -->
        <div class="form-group">
          <label for="voiceSelect">낭독자 목소리</label>
          <div class="voice-row">
            <div class="select-wrapper">
              <select id="voiceSelect" v-model="state.selectedVoice.value">
                <option value="" disabled v-if="state.voices.value.length === 0">불러오는 중...</option>
                <option v-for="voice in state.voices.value" :key="voice.id" :value="voice.id">
                  {{ voice.name }}
                </option>
              </select>
              <i data-lucide="chevron-down" class="select-arrow"></i>
            </div>
            <button 
              type="button" 
              class="btn-voice-preview" 
              aria-label="선택한 목소리 미리듣기" 
              title="선택한 목소리 미리듣기"
              @click="logic.previewVoice"
            >
              <i data-lucide="volume-2"></i>
              <span>미리듣기</span>
            </button>
          </div>
          <div class="voice-desc">{{ logic.selectedVoiceDesc.value }}</div>
        </div>
        <!-- Speed/Rate Slider -->
        <div class="form-group">
          <div class="label-with-val">
            <label for="speedSlider">읽기 속도</label>
            <span class="slider-val">{{ logic.speedLabel.value }}</span>
          </div>
          <input type="range" id="speedSlider" min="0.5" max="2.0" step="0.1" v-model.number="state.speed.value">
        </div>
        <!-- Pitch Slider -->
        <div class="form-group">
          <div class="label-with-val">
            <label for="pitchSlider">목소리 높낮이</label>
            <span class="slider-val">{{ logic.pitchLabel.value }}</span>
          </div>
          <input type="range" id="pitchSlider" min="-50" max="50" step="2" v-model.number="state.pitch.value">
        </div>
      </div>
    </div>
  </div>
  
  <div class="modal-footer" v-if="!state.isGenerating.value">
    <p class="generate-hint" v-if="!authStore.user">Google 계정으로 로그인하면 오디오북을 만들 수 있어요</p>
    <button class="btn btn-primary btn-generate" @click="logic.startGeneration">
      <i data-lucide="sparkles"></i>
      <span>오디오북 만들기</span>
    </button>
  </div>

  <div v-else class="loader-card" style="margin: 2rem 0;">
    <div class="spinner-container">
      <div class="double-bounce1"></div>
      <div class="double-bounce2"></div>
    </div>
    <h3>오디오북 생성 중...</h3>
    <p>문서의 크기에 따라 수 초에서 수 분이 소요될 수 있습니다.</p>
    <div class="progress-container">
      <div class="progress-bar-fill" style="width: 50%; transition: width 1s linear;"></div>
    </div>
    <span class="loading-status">TTS 변환 프로세스 작동 중...</span>
  </div>
</template>
