<script lang="ts">
import type { ThemeState, AppTheme } from "./Theme_State.vue";

const STORAGE_KEY = "textAudio_appTheme";
const VALID_THEMES: AppTheme[] = ["light", "dark", "warm", "gray"];

export interface ThemeLogic {
    openSheet(): void;
    closeSheet(): void;
    selectTheme(theme: AppTheme): void;
}

// 앱 전체(홈/보관함/리더/관리자) 배색을 <html>의 data-app-theme 속성으로
// 전환한다. style.css/admin.css의 :root[data-app-theme="..."] 규칙이 실제
// 색상을 정의한다. main.ts(메인 SPA)와 main-admin.ts(관리자)는 서로 다른
// 번들이라 각자 이 컴포저블을 부르지만, 같은 localStorage 키를 공유해
// 한쪽에서 고른 테마가 다른 쪽에서도 유지된다. document는 항상 존재하므로
// (SSR 아님) 별도 onMounted 없이 여기서 바로 적용한다.
export function useThemeLogic(state: ThemeState): ThemeLogic {
    const saved = localStorage.getItem(STORAGE_KEY) as AppTheme | null;
    if (saved && VALID_THEMES.includes(saved)) state.activeTheme.value = saved;
    document.documentElement.setAttribute("data-app-theme", state.activeTheme.value);

    function openSheet(): void {
        state.isSheetOpen.value = true;
    }

    function closeSheet(): void {
        state.isSheetOpen.value = false;
    }

    function selectTheme(theme: AppTheme): void {
        state.activeTheme.value = theme;
        localStorage.setItem(STORAGE_KEY, theme);
        document.documentElement.setAttribute("data-app-theme", theme);
    }

    return { openSheet, closeSheet, selectTheme };
}

export default {};
</script>
