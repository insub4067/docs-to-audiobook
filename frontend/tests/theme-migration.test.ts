import { describe, it, expect, beforeEach } from "vitest";

import { useThemeState, APP_THEME_OPTIONS } from "../Theme/Theme_State.vue";
import { useThemeLogic } from "../Theme/Theme_Logic.vue";

// 없앤 "그레이" 테마를 쓰던 기기가 앱을 다시 열었을 때 무슨 일이 벌어지는지를
// 못박는다. 검증 목록에서 빠졌으니 그냥 두면 기본값(웜 = 밝은 종이색)으로
// 떨어지는데, 어두운 테마를 쓰던 사람이 앱을 열자마자 흰 화면을 보게 된다.

const STORAGE_KEY = "textAudio_appTheme";

function applyStoredTheme() {
    const state = useThemeState();
    useThemeLogic(state);
    return state.activeTheme.value;
}

describe("테마 마이그레이션", () => {
    beforeEach(() => {
        localStorage.clear();
        document.documentElement.removeAttribute("data-app-theme");
    });

    it("그레이를 쓰던 기기는 다크로 넘어간다", () => {
        localStorage.setItem(STORAGE_KEY, "gray");
        expect(applyStoredTheme()).toBe("dark");
    });

    it("넘어간 뒤에는 저장값도 다크로 바뀌어 매번 다시 옮기지 않는다", () => {
        localStorage.setItem(STORAGE_KEY, "gray");
        applyStoredTheme();
        expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    });

    it("<html> 속성에도 다크가 반영된다", () => {
        localStorage.setItem(STORAGE_KEY, "gray");
        applyStoredTheme();
        expect(document.documentElement.getAttribute("data-app-theme")).toBe("dark");
    });

    it("남은 세 테마는 그대로 유지된다", () => {
        for (const theme of ["light", "dark", "warm"]) {
            localStorage.setItem(STORAGE_KEY, theme);
            expect(applyStoredTheme()).toBe(theme);
        }
    });

    it("모르는 값은 기본값(웜)으로 떨어진다", () => {
        localStorage.setItem(STORAGE_KEY, "neon");
        expect(applyStoredTheme()).toBe("warm");
    });

    it("선택 목록에 그레이가 남아 있지 않다", () => {
        expect(APP_THEME_OPTIONS.map((o) => o.value)).toEqual(["light", "dark", "warm"]);
    });
});
