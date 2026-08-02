import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import HomeView from "../Home/Home_View.vue";

// 백엔드가 실제로 이 SPA(app.html)를 서빙하는 경로는 "/"와 "/share/:id"
// 뿐이다(backend/routes/system.py, share.py). 그 외 경로는 admin.html
// 처럼 아예 다른 파일을 서빙하거나 백엔드에 라우트가 없어 여기까지
// 오지 않는다. 공유 링크의 shareId는 Reader_Logic.checkSharedLink()가
// location.pathname을 직접 파싱하므로 라우트 파라미터는 쓰지 않는다.
const routes: RouteRecordRaw[] = [
    { path: "/", component: HomeView },
    { path: "/share/:shareId", component: HomeView },
];

const router = createRouter({
    history: createWebHistory(),
    routes,
});

export default router;
