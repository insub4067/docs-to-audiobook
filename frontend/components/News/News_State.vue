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
    // 목록 안의 audio_url/sentences_url은 1시간짜리 서명 URL이다. 언제
    // 받아 왔는지 알아야 만료 전에 다시 받을 수 있다(services/signedUrls.ts).
    fetchedAt: Ref<number>;
    isListOpen: Ref<boolean>;
    // 지금 재생 중인 기사가 목록에서 몇 번째인가. 개별 기사를 눌러 들을
    // 때도 채워진다 — "전체 반복"이면 어떻게 시작했든 목록을 순환해야 해서
    // 위치를 항상 알고 있어야 한다.
    queueIndex: Ref<number>;
    // "전체 듣기"로 시작한 연속 재생인가. 반복이 꺼져 있을 때 다음 기사로
    // 자동으로 넘어갈지를 가른다(개별 재생은 한 기사만 듣고 끝난다).
    isContinuous: Ref<boolean>;
}

// 홈의 요약 카드와 전체 목록 시트가 같은 목록/재생 큐를 공유해야 해서
// Toast/PromptSheet와 같은 모듈 싱글턴 패턴을 쓴다.
const state: NewsState = {
    items: ref([]),
    loaded: ref(false),
    fetchedAt: ref(0),
    isListOpen: ref(false),
    queueIndex: ref(-1),
    isContinuous: ref(false),
};

export function useNewsState(): NewsState {
    return state;
}

export default {};
</script>
