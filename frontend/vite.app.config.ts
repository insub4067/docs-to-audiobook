import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 메인 SPA 포팅을 검증하기 위한 별도 빌드 설정. 업로드·보관함·리더까지
// 다 옮기고 검증하기 전까지는 어떤 백엔드 라우트도 이 결과물을 서빙하지
// 않는다 — vite.config.ts(관리자 대시보드, 이미 프로덕션에서 씀)는
// 건드리지 않는다.
export default defineConfig({
    plugins: [vue()],
    base: "/static/dist/app/",
    build: {
        outDir: "static/dist/app",
        emptyOutDir: true,
        rollupOptions: {
            input: "app.html",
        },
    },
});
