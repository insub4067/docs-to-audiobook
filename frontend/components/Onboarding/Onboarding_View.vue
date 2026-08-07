<script setup lang="ts">
// 처음 온 사람에게 "이걸로 뭘 하는지"를 알려주는 카드.
//
// 가입자 6명 중 4명이 아무것도 하지 않고 떠났다. 홈에 들어가면 업로드 카드,
// 경제 뉴스, 최근 추가가 한꺼번에 보이는데 이 앱이 무엇을 하는 물건인지는
// 어디에도 적혀 있지 않다. iOS "말하기 화면"이 무료로 기본 탑재된 상황에서
// "왜 이걸 써야 하는가"에 답하지 않으면 남을 이유가 없다.
//
// 온보딩 흐름을 만들지는 않았다. 여러 단계짜리 튜토리얼은 지금 사용자 수에
// 비해 과하고, 무엇보다 첫 화면을 한 겹 더 가린다. 한 문단과 버튼 하나면
// 충분하다는 판단이다.
//
// State/Logic으로 쪼개지 않은 것도 의도다. 이 컴포넌트 밖에서 읽거나 바꿀
// 상태가 없다(닫았는지 여부는 localStorage가 진실이다). services/indexedDb.ts와
// 같은 이유로, 나눌 것이 없을 때는 나누지 않는다.
import { computed, ref } from "vue";
import type { AudioListState } from "../Library/AudioList_State.vue";
import type { AudioListLogic } from "../Library/AudioList_Logic.vue";

const props = defineProps<{
    state: AudioListState;
    logic: AudioListLogic;
}>();

const DISMISSED_KEY = "textAudio_onboardingDismissed";

const dismissed = ref(localStorage.getItem(DISMISSED_KEY) === "1");

/** 기본 제공 오디오북은 첫 방문자에게도 이미 깔려 있다. 그게 곧 샘플이다 —
 *  체험을 위해 따로 무언가를 만들 필요가 없다. */
const sampleBook = computed(() => props.state.savedAudiobooks.value.find((audio) => audio.isDefault));

/** 자기 것을 하나라도 만들었으면 안내는 할 일을 다 한 것이다. */
const hasOwnAudiobook = computed(() => props.state.savedAudiobooks.value.some((audio) => !audio.isDefault));

const visible = computed(() => !dismissed.value && !hasOwnAudiobook.value);

function dismiss(): void {
    localStorage.setItem(DISMISSED_KEY, "1");
    dismissed.value = true;
}

async function playSample(): Promise<void> {
    const book = sampleBook.value;
    if (!book) return;
    await props.logic.openItem(book);
}
</script>

<template>
    <section v-if="visible" class="glass-card onboarding-card">
        <button class="onboarding-dismiss" type="button" aria-label="안내 닫기" @click="dismiss">
            <i data-lucide="x"></i>
        </button>

        <h2 class="onboarding-title">읽을 시간이 없는 문서를, 듣는 책으로</h2>
        <p class="onboarding-body">
            PDF·웹페이지·유튜브를 넣으면 오디오북으로 바꿔 드려요.
            듣는 동안 지금 읽는 문장이 따라 움직이고, 만든 책은 파일로 남아
            언제든 멈춘 자리에서 이어 들을 수 있어요.
        </p>

        <button
            v-if="sampleBook"
            class="onboarding-sample"
            type="button"
            @click="playSample"
        >
            <i data-lucide="play"></i>
            <span>샘플 들어보기</span>
        </button>
    </section>
</template>
