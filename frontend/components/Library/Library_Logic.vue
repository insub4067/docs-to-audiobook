<script lang="ts">
import type { LibraryState } from './Library_State.vue';
import { useLibraryStore } from '../../stores/library';
import { usePlayerStore } from '../../stores/player';
import { useActionSheet } from '../../composables/useActionSheet';
import { useToast } from '../../composables/useToast';
import { onMounted } from 'vue';

export interface LibraryLogic {
  loadLibrary: () => Promise<void>;
  playAudiobook: (book: any) => void;
  openOptions: (book: any) => void;
  deleteAudiobook: (id: string) => Promise<void>;
  formatDate: (dateString: string) => string;
}

export function useLibraryLogic({ isLoading }: LibraryState): LibraryLogic {
  const libraryStore = useLibraryStore();
  const playerStore = usePlayerStore();
  const actionSheet = useActionSheet();
  const toast = useToast();

  async function loadLibrary() {
    isLoading.value = true;
    try {
      // Mock loading from DB
      // In a real app, this would fetch from IndexedDB using db.js
      setTimeout(() => {
        if (libraryStore.audiobooks.length === 0) {
          // Dummy data just for UI testing
          libraryStore.setAudiobooks([
            { id: '1', title: '샘플 오디오북 1', created_at: new Date().toISOString(), status: 'completed', sentences: [] },
            { id: '2', title: '실패한 오디오북', created_at: new Date().toISOString(), status: 'failed', sentences: [] }
          ]);
        }
        isLoading.value = false;
      }, 500);
    } catch (error) {
      console.error(error);
      isLoading.value = false;
      toast.showToast('라이브러리를 불러오는데 실패했습니다.', 'error');
    }
  }

  function playAudiobook(book: any) {
    if (book.status !== 'completed') {
      toast.showToast('생성 완료된 오디오북만 재생할 수 있습니다.', 'info');
      return;
    }
    playerStore.openReader(book);
  }

  function openOptions(book: any) {
    actionSheet.show([
      { label: '공유', icon: 'share-2', action: () => toast.showToast('공유 링크가 복사되었습니다.', 'success') },
      { label: '다운로드', icon: 'download', action: () => toast.showToast('다운로드를 시작합니다.', 'info') },
      { label: '삭제', icon: 'trash-2', isDanger: true, action: () => deleteAudiobook(book.id) },
    ], book.title);
  }

  async function deleteAudiobook(id: string) {
    // Delete from IndexedDB and state
    libraryStore.removeAudiobook(id);
    toast.showToast('삭제되었습니다.', 'success');
  }

  function formatDate(dateString: string) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`;
  }

  onMounted(() => {
    loadLibrary();
  });

  return {
    loadLibrary,
    playAudiobook,
    openOptions,
    deleteAudiobook,
    formatDate
  };
}

export default {};
</script>
