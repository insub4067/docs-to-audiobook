<script lang="ts">
import { ref, type Ref } from "vue";

export interface NewsItem {
    id: string;
    title: string;
    news_category: string | null;
    news_source: string | null;
    created_at: string;
    audio_url: string;
    sentences_url: string | null;
    duration_seconds: number | null;
}

export interface NewsState {
    items: Ref<NewsItem[]>;
    loaded: Ref<boolean>;
    isListOpen: Ref<boolean>;
    queueIndex: Ref<number>;
}

// 홈의 요약 카드와 전체 목록 시트가 같은 목록/재생 큐를 공유해야 해서
// Toast/PromptSheet와 같은 모듈 싱글턴 패턴을 쓴다.
const state: NewsState = {
    items: ref([]),
    loaded: ref(false),
    isListOpen: ref(false),
    queueIndex: ref(-1),
};

export function useNewsState(): NewsState {
    return state;
}

export default {};
</script>
