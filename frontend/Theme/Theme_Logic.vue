<script lang="ts">
import type { ThemeState, AppTheme } from "./Theme_State.vue";

const STORAGE_KEY = "textAudio_appTheme";
const VALID_THEMES: AppTheme[] = ["light", "dark", "warm"];

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
    // 없앤 "그레이"를 쓰던 기기는 다크로 넘긴다. 그냥 두면 검증에서 걸러져
    // 기본값(웜 = 밝은 종이색)으로 떨어지는데, 어두운 테마를 쓰던 사람이
    // 앱을 열자마자 흰 화면을 보게 된다. 저장값도 함께 고쳐 매번 다시
    // 옮기지 않게 한다.
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "gray") localStorage.setItem(STORAGE_KEY, "dark");
    const theme = (saved === "gray" ? "dark" : saved) as AppTheme | null;
    if (theme && VALID_THEMES.includes(theme)) state.activeTheme.value = theme;
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
