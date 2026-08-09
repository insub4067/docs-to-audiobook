<script lang="ts">
import { ref, type Ref } from "vue";

export type AppTheme = "light" | "dark" | "warm";

export interface AppThemeOption {
    value: AppTheme;
    label: string;
    swatchBg: string;
}

export const APP_THEME_OPTIONS: AppThemeOption[] = [
    { value: "light", label: "라이트", swatchBg: "#ffffff" },
    { value: "dark", label: "다크", swatchBg: "#121212" },
    { value: "warm", label: "웜", swatchBg: "#FAF5E6" },
];

export interface ThemeState {
    activeTheme: Ref<AppTheme>;
    isSheetOpen: Ref<boolean>;
}

export function useThemeState(): ThemeState {
    return {
        activeTheme: ref("warm"),
        isSheetOpen: ref(false),
    };
}

export default {};
</script>
