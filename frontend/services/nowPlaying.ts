// 지금 재생 중인 항목의 id.
//
// 목록 화면마다 "이 행이 지금 듣고 있는 것인가"를 알아야 하는데,
// Reader_State는 호출할 때마다 새 객체를 만드는 팩토리라 컴포넌트끼리
// 공유할 수 없다. 홈·내 파일·서점이 각자 리더 상태를 prop으로 받아 내려가면
// 중간 컴포넌트가 쓰지도 않는 값을 계속 넘겨야 한다.
//
// "무엇이 재생 중인가"는 화면에 딸린 상태가 아니라 앱 전체의 상태라서,
// Toast·News_State와 같은 모듈 싱글턴으로 둔다.
//
// 개인 오디오북(IndexedDB id)과 라이브러리 작품(서버 id)이 같은 자리를 쓴다.
// 둘 다 안정적인 id를 갖고 있어 한 값으로 다룰 수 있다(북마크가 이미 같은
// 이유로 두 종류를 한 스토어에 담는다).
import { ref, type Ref } from "vue";

export const nowPlayingId: Ref<string | null> = ref(null);

// id만으로는 "지금 듣는 것"과 "듣다 멈춘 것"을 구분할 수 없다. 목록에서
// 재생 중인 행에 ▶가 남아 있어 "재생 중인가, 눌러야 하는가"가 모호했는데,
// 그걸 고치려면 화면이 재생 상태를 알아야 한다.
//
// loading·finished·error는 넣지 않는다. 지금 그 상태를 만드는 코드가 없어
// 죽은 분기가 된다 — 필요해질 때 그때 늘린다.
export type NowPlayingState = "playing" | "paused";

export const nowPlayingState: Ref<NowPlayingState> = ref("paused");

export function setNowPlaying(id: string | null, state: NowPlayingState = "playing"): void {
    nowPlayingId.value = id;
    nowPlayingState.value = id ? state : "paused";
}

export function setNowPlayingState(state: NowPlayingState): void {
    // 아무것도 재생 중이 아닐 때 들어오는 pause 이벤트는 무시한다.
    if (nowPlayingId.value) nowPlayingState.value = state;
}
