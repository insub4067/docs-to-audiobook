<script lang="ts">
import { ref, type Ref } from "vue";

export type ReaderTheme = "light" | "dark" | "warm" | "gray";

export interface ReaderThemeOption {
    value: ReaderTheme;
    label: string;
    swatchBg: string;
}

export const READER_THEME_OPTIONS: ReaderThemeOption[] = [
    { value: "light", label: "라이트", swatchBg: "#ffffff" },
    { value: "dark", label: "다크", swatchBg: "#121212" },
    { value: "warm", label: "웜", swatchBg: "#FAF5E6" },
    { value: "gray", label: "그레이", swatchBg: "#e7e7e5" },
];

export interface ReaderThemeState {
    activeTheme: Ref<ReaderTheme>;
    isSheetOpen: Ref<boolean>;
}

export function useReaderThemeState(): ReaderThemeState {
    return {
        activeTheme: ref("warm"),
        isSheetOpen: ref(false),
    };
}

export default {};
</script>
