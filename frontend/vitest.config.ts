import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// 컴포넌트 회귀 테스트 전용 설정. 빌드 설정(vite.app.config.ts /
// vite.config.ts)과 분리해 둔다 — 여기서는 base/outDir 같은 배포용
// 설정이 필요 없고, 반대로 빌드에는 jsdom 환경이 필요 없다.
export default defineConfig({
    plugins: [vue()],
    test: {
        environment: "jsdom",
        include: ["tests/**/*.test.ts"],
        setupFiles: ["tests/setup.ts"],
        // jsdom은 origin이 opaque면(기본 about:blank) localStorage를 아예
        // 노출하지 않는다 — 테마/재생 설정이 localStorage를 읽으므로 실제
        // origin을 준다.
        environmentOptions: { jsdom: { url: "http://localhost:8000" } },
    },
});
