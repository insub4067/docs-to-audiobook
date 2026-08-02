<script lang="ts">
import { ref, type Ref } from "vue";

export interface PwaState {
    pullDistance: Ref<number>;
    pullProgress: Ref<number>;
    pullOpacity: Ref<number>;
    isPullActive: Ref<boolean>;
    isPullSettling: Ref<boolean>;
    isRefreshing: Ref<boolean>;
    versionLabel: Ref<string>;
    isIosPromptVisible: Ref<boolean>;
}

// 앱 전체에서 하나뿐인 셸 상태(당겨서 새로고침, 버전 표시, iOS 설치 안내)라
// Toast_State.vue와 마찬가지로 모듈 싱글턴으로 둔다 — App.vue와
// Home_View.vue가 서로 다른 인스턴스를 갖고 어긋나면 안 된다.
const state: PwaState = {
    pullDistance: ref(0),
    pullProgress: ref(0),
    pullOpacity: ref(0),
    isPullActive: ref(false),
    isPullSettling: ref(false),
    isRefreshing: ref(false),
    versionLabel: ref("v --"),
    isIosPromptVisible: ref(false),
};

export function usePwaState(): PwaState {
    return state;
}

export default {};
</script>
