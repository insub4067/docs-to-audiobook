// 구글 드라이브에서 파일 하나를 고르는 흐름. GoogleSignIn.ts가 쓰는
// window.google.accounts.id(로그인용 ID 토큰)와는 별개로,
// window.google.accounts.oauth2(액세스 토큰)를 써서 drive.file
// 스코프만 요청한다 — 사용자가 Picker에서 직접 고른 파일에만 접근하는
// 최소 권한 스코프다. Picker 자체는 gapi(별도 스크립트)로 그린다.

declare global {
    interface Window {
        google?: any;
        gapi?: any;
    }
}

const DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file";

let pickerLibraryPromise: Promise<void> | null = null;

function loadScriptOnce(src: string): Promise<void> {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) return resolve();
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.defer = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("구글 스크립트를 불러오지 못했습니다."));
        document.head.appendChild(script);
    });
}

function waitFor(check: () => boolean, timeoutMs = 8000): Promise<boolean> {
    return new Promise((resolve) => {
        const start = Date.now();
        (function poll() {
            if (check()) return resolve(true);
            if (Date.now() - start > timeoutMs) return resolve(false);
            setTimeout(poll, 100);
        })();
    });
}

async function ensureOAuthClientReady(): Promise<void> {
    if (!(await waitFor(() => !!window.google?.accounts?.oauth2))) {
        throw new Error("Google 로그인 스크립트를 불러오지 못했습니다.");
    }
}

async function ensurePickerLoaded(): Promise<void> {
    if (!pickerLibraryPromise) {
        pickerLibraryPromise = (async () => {
            await loadScriptOnce("https://apis.google.com/js/api.js");
            if (!(await waitFor(() => !!window.gapi))) throw new Error("구글 API를 불러오지 못했습니다.");
            await new Promise<void>((resolve, reject) => {
                window.gapi.load("picker", { callback: resolve, onerror: () => reject(new Error("Picker API를 불러오지 못했습니다.")) });
            });
        })();
    }
    return pickerLibraryPromise;
}

function requestDriveAccessToken(clientId: string): Promise<string> {
    return new Promise((resolve, reject) => {
        const tokenClient = window.google.accounts.oauth2.initTokenClient({
            client_id: clientId,
            scope: DRIVE_SCOPE,
            callback: (response: { access_token?: string; error?: string; error_description?: string }) => {
                if (response.error || !response.access_token) {
                    reject(new Error(response.error_description || "구글 드라이브 접근 권한을 받지 못했습니다."));
                } else {
                    resolve(response.access_token);
                }
            },
        });
        tokenClient.requestAccessToken({ prompt: "" });
    });
}

function openPicker(accessToken: string, apiKey: string): Promise<{ id: string; name: string } | null> {
    return new Promise((resolve, reject) => {
        try {
            const view = new window.google.picker.DocsView()
                .setIncludeFolders(false)
                .setSelectFolderEnabled(false);
            const builder = new window.google.picker.PickerBuilder()
                .addView(view)
                .setOAuthToken(accessToken)
                .setCallback((data: any) => {
                    if (data.action === window.google.picker.Action.PICKED) {
                        const doc = data.docs[0];
                        resolve({ id: doc.id, name: doc.name });
                    } else if (data.action === window.google.picker.Action.CANCEL) {
                        resolve(null);
                    }
                });
            if (apiKey) builder.setDeveloperKey(apiKey);
            builder.build().setVisible(true);
        } catch (error) {
            reject(error as Error);
        }
    });
}

export interface PickedDriveFile {
    fileId: string;
    accessToken: string;
    name: string;
}

/** 사용자가 취소하면 null을 돌려준다(에러가 아니다). */
export async function pickGoogleDriveFile(clientId: string, apiKey: string): Promise<PickedDriveFile | null> {
    await ensureOAuthClientReady();
    await ensurePickerLoaded();
    const accessToken = await requestDriveAccessToken(clientId);
    const picked = await openPicker(accessToken, apiKey);
    if (!picked) return null;
    return { fileId: picked.id, accessToken, name: picked.name };
}
