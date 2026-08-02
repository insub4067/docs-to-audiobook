<script lang="ts">
import type { ReaderThemeState, ReaderTheme } from "./ReaderTheme_State.vue";

const STORAGE_KEY = "textAudio_readerTheme";
const VALID_THEMES: ReaderTheme[] = ["light", "dark", "warm", "gray"];

export interface ReaderThemeLogic {
    initialize(): void;
    openSheet(): void;
    closeSheet(): void;
    selectTheme(theme: ReaderTheme): void;
}

// 리더 화면 전용 배색(라이트/다크/웜/그레이). 앱 전체 색상(--bg-color 등)과
// 별개로 .reader-container에 data-reader-theme 속성을 달아 CSS
// 변수(--reader-bg 등, style.css)로 적용한다. 새로고침해도 유지되도록
// localStorage에 저장한다.
//
// containerEl은 View의 template ref라 setup 시점에는 아직 비어 있다
// (mount 후에야 채워진다) — initialize()를 View의 onMounted에서 불러야
// 첫 렌더에 테마가 반영된다.
export function useReaderThemeLogic(state: ReaderThemeState, containerEl: { value: HTMLElement | null }): ReaderThemeLogic {
    const saved = localStorage.getItem(STORAGE_KEY) as ReaderTheme | null;
    if (saved && VALID_THEMES.includes(saved)) state.activeTheme.value = saved;

    function applyToContainer(): void {
        containerEl.value?.setAttribute("data-reader-theme", state.activeTheme.value);
    }

    function initialize(): void {
        applyToContainer();
    }

    function openSheet(): void {
        state.isSheetOpen.value = true;
    }

    function closeSheet(): void {
        state.isSheetOpen.value = false;
    }

    function selectTheme(theme: ReaderTheme): void {
        state.activeTheme.value = theme;
        localStorage.setItem(STORAGE_KEY, theme);
        applyToContainer();
        closeSheet();
    }

    return { initialize, openSheet, closeSheet, selectTheme };
}

export default {};
</script>
