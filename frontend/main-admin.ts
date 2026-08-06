import { createApp } from "vue";
import AdminView from "./Admin/Admin_View.vue";

// 홈 화면에 추가한 PWA(standalone)에서는 레이아웃 뷰포트(innerHeight)가 실제
// 화면보다 상태바 높이만큼 짧게 잡힌다 — 실기기 계측 결과 innerHeight=793,
// screen.height=852, 100vh=852였다. 그래서 position:fixed + bottom:0으로
// 붙인 시트가 화면 바닥이 아니라 793에서 끝나 아래에 59pt의 빈 띠가 남았다.
// 이 상태에서만 시트 백드롭 높이를 100vh로 잡아 화면 끝까지 닿게 한다
// (Safari에서는 100vh가 툴바 뒤까지 잡혀 오히려 시트가 가려지므로 제외).
if ((navigator as unknown as { standalone?: boolean }).standalone === true) {
    document.documentElement.classList.add("ios-standalone");
}

createApp(AdminView).mount("#app");
