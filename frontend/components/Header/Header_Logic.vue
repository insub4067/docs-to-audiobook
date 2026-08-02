<script lang="ts">
import { useRouter } from "vue-router";
import type { HeaderState } from "./Header_State.vue";
import { useAuthStore } from "../../stores/auth";
import { useAuthLogic } from "../../Auth/Auth_Logic.vue";
import { renderGoogleButton } from "../../Auth/GoogleSignIn";

export interface HeaderLogic {
    toggleProfileMenu(): void;
    closeProfileMenu(event: MouseEvent): void;
    handleLogout(): Promise<void>;
    handleLogoTap(): void;
    setupSocialLogin(): Promise<void>;
}

// 관리자만 로고를 3번 연속 탭하면 /admin으로 이동한다(브랜드 텍스트만으로는
// 관리자 진입점이 눈에 띄면 안 되므로 숨겨진 제스처로 둔다).
const LOGO_TAP_WINDOW_MS = 700;
const LOGO_TAP_COUNT_TO_ADMIN = 3;

export function useHeaderLogic({ isProfileMenuOpen, authError, googleButtonSlots }: HeaderState): HeaderLogic {
    const authStore = useAuthStore();
    const authLogic = useAuthLogic();
    const router = useRouter();

    let logoTapCount = 0;
    let logoTapTimer: ReturnType<typeof setTimeout> | undefined;

    function toggleProfileMenu(): void {
        isProfileMenuOpen.value = !isProfileMenuOpen.value;
    }

    function closeProfileMenu(event: MouseEvent): void {
        const target = event.target as HTMLElement;
        if (isProfileMenuOpen.value && !target.closest(".user-info")) {
            isProfileMenuOpen.value = false;
        }
    }

    async function handleLogout(): Promise<void> {
        isProfileMenuOpen.value = false;
        await authLogic.logout();
    }

    function handleLogoTap(): void {
        if (!authStore.isAdmin) return;
        logoTapCount += 1;
        clearTimeout(logoTapTimer);
        logoTapTimer = setTimeout(() => { logoTapCount = 0; }, LOGO_TAP_WINDOW_MS);
        if (logoTapCount === LOGO_TAP_COUNT_TO_ADMIN) {
            logoTapCount = 0;
            router.push("/admin");
        }
    }

    /** 헤더/로그인 카드 두 슬롯 모두에 구글 버튼을 그린다. 슬롯은
     * Header_View가 마운트 시 googleButtonSlots에 등록한다. */
    async function setupSocialLogin(): Promise<void> {
        const slots = googleButtonSlots.value.filter((el): el is HTMLElement => !!el);
        if (slots.length === 0) return;

        try {
            const config = await fetch("/api/config").then((r) => r.json());
            const clientId = config.providers?.google;
            if (!clientId) {
                authError.value = "로그인 설정이 준비되지 않았습니다. 관리자에게 문의해 주세요.";
                return;
            }

            for (const slot of slots) {
                try {
                    await renderGoogleButton(slot, clientId, (credential) => {
                        authLogic.completeSocialLogin("google", credential).catch((error) => {
                            authError.value = error.message || "로그인에 실패했습니다.";
                        });
                    });
                } catch (error) {
                    console.error("google 로그인 버튼 렌더 실패:", error);
                    authError.value = (error as Error).message || "로그인을 준비하지 못했습니다.";
                }
            }
        } catch (error) {
            console.error("Social login setup failed:", error);
            authError.value = "로그인을 준비하지 못했습니다.";
        }
    }

    return { toggleProfileMenu, closeProfileMenu, handleLogout, handleLogoTap, setupSocialLogin };
}

export default {};
</script>
