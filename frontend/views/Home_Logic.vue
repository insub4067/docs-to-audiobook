<script lang="ts">
import type { HomeState } from './Home_State.vue';
import { useToast } from '../composables/useToast';

export interface HomeLogic {
  handleDragOver: (e: DragEvent) => void;
  handleDragLeave: (e: DragEvent) => void;
  handleDrop: (e: DragEvent) => void;
  handleFileSelect: (e: Event) => void;
  clearUrl: () => void;
  fetchUrl: () => Promise<void>;
}

export function useHomeLogic({ isDragging, isUploading, urlInput }: HomeState): HomeLogic {
  const toast = useToast();

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (!isDragging.value) isDragging.value = true;
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    isDragging.value = false;
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    isDragging.value = false;
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      processFiles(Array.from(files));
    }
  }

  function handleFileSelect(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      processFiles(Array.from(input.files));
    }
    input.value = ''; // Reset input
  }

  function processFiles(files: File[]) {
    // Basic validation
    const validExtensions = ['.docx', '.pdf', '.txt', '.md', '.markdown', '.hwp'];
    const validFiles = files.filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
      return validExtensions.includes(ext);
    });

    if (validFiles.length === 0) {
      toast.showToast('지원하지 않는 파일 형식입니다.', 'error');
      return;
    }

    if (validFiles.some(f => f.size > 10 * 1024 * 1024)) {
      toast.showToast('10MB 이하의 파일만 업로드할 수 있습니다.', 'error');
      return;
    }

    // Process valid files (Mock logic, will trigger modal or API call)
    isUploading.value = true;
    setTimeout(() => {
      isUploading.value = false;
      toast.showToast(`${validFiles.length}개의 파일을 성공적으로 읽었습니다.`, 'success');
      // Here we would typically open the generation modal
    }, 1500);
  }

  function clearUrl() {
    urlInput.value = '';
  }

  async function fetchUrl() {
    if (!urlInput.value) {
      toast.showToast('URL을 입력해주세요.', 'error');
      return;
    }
    
    try {
      new URL(urlInput.value); // Validate URL format
    } catch {
      toast.showToast('올바른 URL 형식이 아닙니다.', 'error');
      return;
    }

    isUploading.value = true;
    setTimeout(() => {
      isUploading.value = false;
      toast.showToast('URL에서 텍스트를 성공적으로 가져왔습니다.', 'success');
      // Open generation modal...
    }, 1500);
  }

  return {
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelect,
    clearUrl,
    fetchUrl
  };
}

export default {};
</script>
