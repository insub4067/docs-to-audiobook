import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 빌드 결과물은 이 프로젝트 안의 static/(FastAPI가 그대로 서빙) 아래에 둔다.
// base를 절대 경로로 고정해야, 라우트가 이 HTML의 내용을 그대로 응답해도
// 자산 경로가 깨지지 않는다. URL 경로("/static/...")는 FastAPI가 
// frontend/static을 "/static"으로 마운트하므로 바뀌지 않는다.
export default defineConfig({
    plugins: [vue()],
    base: "/static/dist/spa/",
    build: {
        outDir: "static/dist/spa",
        emptyOutDir: true,
        rollupOptions: {
            input: "index.html",
        },
    },
});
