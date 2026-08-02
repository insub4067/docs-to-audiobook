import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import HomeView from "../views/Home_View.vue";

// 이 라우터는 아직 어떤 백엔드 라우트에도 연결되지 않은, 새 메인 SPA를
// 검증하기 위한 것이다(admin.html의 관리자 대시보드와는 별개). 업로드·
// 보관함·리더까지 다 옮기고 검증한 뒤에 실제 "/" 라우트로 교체한다.
const routes: RouteRecordRaw[] = [
    { path: "/", component: HomeView },
    // 테스트 중엔 정적 빌드 파일 경로(/static/dist/app/app.html)로 직접
    // 열어서 확인하므로, "/"와 매칭되지 않는 나머지도 Home으로 보낸다.
    // 실제 "/" 라우트로 교체할 때 제거한다.
    { path: "/:pathMatch(.*)*", component: HomeView },
];

const router = createRouter({
    history: createWebHistory(),
    routes,
});

export default router;
