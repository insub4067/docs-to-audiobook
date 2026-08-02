import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 메인 SPA(업로드/생성/보관함/리더) 빌드 설정. "/"와 "/share/:id"가 이
// 결과물(app.html)을 서빙한다(backend/routes/system.py, share.py).
// vite.config.ts(관리자 대시보드)와는 별개 빌드다.
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
