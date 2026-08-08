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

export function setNowPlaying(id: string | null): void {
    nowPlayingId.value = id;
}
