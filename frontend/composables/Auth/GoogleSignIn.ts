// static/js/auth.js의 waitForGoogleSdk/SOCIAL_PROVIDERS.google를 그대로 옮긴다.
// GSI는 팝업을 프로그램으로 열 수 없어 구글이 그린 버튼만 열 수 있으므로,
// 공식 버튼을 슬롯에 그대로 렌더한다(One Tap/prompt는 안 씀).

declare global {
    interface Window {
        google?: any;
    }
}

let initialized = false;

/** GSI 스크립트는 async defer로 로드되므로 준비될 때까지 기다린다. */
function waitForGoogleSdk(timeoutMs = 8000): Promise<boolean> {
    return new Promise((resolve) => {
        const start = Date.now();
        (function check() {
            if (window.google && window.google.accounts && window.google.accounts.id) return resolve(true);
            if (Date.now() - start > timeoutMs) return resolve(false);
            setTimeout(check, 100);
        })();
    });
}

export async function renderGoogleButton(
    slot: HTMLElement,
    clientId: string,
    onCredential: (credential: string) => void
): Promise<void> {
    if (!(await waitForGoogleSdk())) {
        throw new Error("Google 로그인 스크립트를 불러오지 못했습니다.");
    }
    if (!initialized) {
        window.google!.accounts.id.initialize({
            client_id: clientId,
            callback: (res: { credential: string }) => onCredential(res.credential),
            ux_mode: "popup",
        });
        initialized = true;
    }
    slot.innerHTML = "";
    window.google!.accounts.id.renderButton(slot, {
        type: "standard",
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "signin_with",
    });
}
