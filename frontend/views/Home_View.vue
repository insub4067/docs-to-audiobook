<script setup lang="ts">
import { useHomeState } from './Home_State.vue';
import { useHomeLogic } from './Home_Logic.vue';
import HeaderView from '../components/AppHeader/Header_View.vue';
import LibraryView from '../components/Library/Library_View.vue';
import ReaderView from '../components/Reader/Reader_View.vue';
import GenerationView from '../components/Generation/Generation_View.vue';
import BaseModal from '../components/ui/BaseModal.vue';
import { useModal } from '../composables/useModal';
import { ref, onMounted, onUpdated } from 'vue';
import lucide from 'lucide';

const state = useHomeState();
const logic = useHomeLogic(state);
const modal = useModal();
const fileInput = ref<HTMLInputElement | null>(null);

function triggerFileInput() {
  fileInput.value?.click();
}

onMounted(() => {
  if (typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});

onUpdated(() => {
  if (typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});
</script>

<template>
  <div class="app-container">
    <!-- Header -->
    <HeaderView />

    <main class="app-main" id="appMain">
      <!-- Upload Section -->
    <section class="glass-card upload-section">
      <div class="card-header">
        <i data-lucide="file-up" class="header-icon"></i>
        <h2>문서 업로드</h2>
      </div>
      
      <div 
        class="upload-dropzone" 
        :class="{ 'dropzone-active': state.isDragging.value }"
        id="dropzone"
        @dragover="logic.handleDragOver"
        @dragleave="logic.handleDragLeave"
        @drop="logic.handleDrop"
        @click="triggerFileInput"
      >
        <input 
          type="file" 
          ref="fileInput" 
          id="fileInput" 
          accept=".docx,.pdf,.txt,.md,.markdown,.hwp" 
          multiple 
          style="display: none;"
          @change="logic.handleFileSelect"
        >
        
        <div id="dropzoneNormal" v-show="!state.isUploading.value">
          <i data-lucide="upload-cloud" class="dropzone-icon"></i>
          <p class="dropzone-text">파일을 이곳에 끌어다 놓거나 터치하세요</p>
          <p class="dropzone-hint">지원 파일: DOCX, PDF, TXT, MD, HWP (최대 10MB, 복수 선택 가능)</p>
        </div>
        
        <div id="dropzoneLoading" v-show="state.isUploading.value" style="text-align: center; color: var(--text-muted);">
          <div class="spinner-container" style="width: 32px; height: 32px; margin: 0 auto 12px;">
            <div class="double-bounce1"></div>
            <div class="double-bounce2"></div>
          </div>
          <p style="font-size: 15px; font-weight: 500;">문서를 분석하고 있습니다...</p>
        </div>
      </div>

      <div class="url-divider"><span>또는</span></div>

      <div class="url-input-row">
        <div class="url-input-wrapper">
          <input 
            type="url" 
            id="urlInput" 
            v-model="state.urlInput.value"
            placeholder="뉴스 기사나 커뮤니티 게시글 링크를 붙여넣으세요" 
            inputmode="url"
            @keyup.enter="logic.fetchUrl"
          >
          <button 
            type="button" 
            class="btn-url-clear" 
            id="urlClearBtn" 
            aria-label="링크 입력 지우기" 
            v-show="state.urlInput.value.length > 0"
            @click="logic.clearUrl"
          >&times;</button>
        </div>
        <button type="button" class="btn-url-fetch" id="urlFetchBtn" @click="logic.fetchUrl" :disabled="state.isUploading.value">
          <i data-lucide="link"></i>
          <span>가져오기</span>
        </button>
      </div>
    </section>

    <!-- Audiobook Library Section -->
    <LibraryView />

    </main>

    <footer class="app-version-footer">
      <span id="appVersionDisplay">v 1.0.0</span>
    </footer>

    <!-- Global Modals & Overlays for Main App -->
    <BaseModal>
      <GenerationView v-if="modal.state.value.component === 'GenerationView'" />
    </BaseModal>

    <ReaderView />
  </div>
</template>
