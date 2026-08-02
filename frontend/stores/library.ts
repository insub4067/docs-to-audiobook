import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface Audiobook {
  id: string;
  title: string;
  sentences: any[];
  audioData?: Uint8Array;
  cloudUrl?: string;
  progress?: number;
  [key: string]: any;
}

export const useLibraryStore = defineStore('library', () => {
  const audiobooks = ref<Audiobook[]>([]);
  const isSyncing = ref(false);

  function setAudiobooks(books: Audiobook[]) {
    audiobooks.value = books;
  }
  
  function addAudiobook(book: Audiobook) {
    audiobooks.value.unshift(book);
  }

  function removeAudiobook(id: string) {
    audiobooks.value = audiobooks.value.filter(b => b.id !== id);
  }

  function updateAudiobook(id: string, updates: Partial<Audiobook>) {
    const book = audiobooks.value.find(b => b.id === id);
    if (book) {
      Object.assign(book, updates);
    }
  }

  return {
    audiobooks,
    isSyncing,
    setAudiobooks,
    addAudiobook,
    removeAudiobook,
    updateAudiobook
  };
});
