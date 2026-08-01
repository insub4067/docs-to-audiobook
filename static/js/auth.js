// ============================================================
// Authentication System
// ============================================================

// 변환 계열 요청에 붙일 인증 헤더. FormData 전송 시 Content-Type을 직접
// 지정하면 boundary가 깨지므로 Authorization만 넣는다.
function authHeaders() {
    const token = localStorage.getItem("authToken");
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

function isLoggedIn() {
    return !!localStorage.getItem("authToken");
}

function anonymousSessionHeaders() {
    let sessionId = localStorage.getItem("anonymousSessionId");
    if (!sessionId) {
        sessionId = crypto.randomUUID();
        localStorage.setItem("anonymousSessionId", sessionId);
    }
    return { "X-Anonymous-Session": sessionId };
}

async function canStartAnonymousTrial() {
    if (isLoggedIn()) return true;
    if (sessionStorage.getItem("anonymousTrialInProgress") === "true") return false;
    if (localStorage.getItem("anonymousTrialUsed") === "true") return false;
    const audiobooks = await getAllAudiobooksFromDB();
    return !audiobooks.some((audiobook) => !audiobook.isDefault);
}

function trackProductEvent(eventName) {
    if (!isLoggedIn()) return;
    fetch("/api/events", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ event_name: eventName }),
    }).catch((error) => console.warn("제품 이벤트 기록 실패:", error));
}

// 설정을 다 마친 뒤 생성 버튼을 눌러서야 로그인이 필요하다는 걸 알면
// 이미 들인 노력이 헛수고처럼 느껴진다. 모달을 여는 시점에 미리 알려준다.
// showAppUI와 applyExtractedText 양쪽에서 호출한다.
function updateGenerateHint() {
    const hint = document.getElementById("generateHint");
    if (!hint) return;
    hint.textContent = isLoggedIn()
        ? ""
        : "로그인 없이 오디오북 한 권을 만들어 볼 수 있어요";
    hint.style.display = isLoggedIn() ? "none" : "block";
}

async function initializeAuth() {
    const token = localStorage.getItem("authToken");
    const authContainer = document.getElementById("authContainer");
    const appMain = document.getElementById("appMain");
    const userInfo = document.getElementById("userInfo");

    if (token) {
        try {
            const user = await fetchCurrentUser(token);
            showAppUI(user, token);
        } catch (error) {
            if (error.authFailed) {
                // 토큰이 실제로 무효하다. 이때만 지운다.
                localStorage.removeItem("authToken");
                showAppUI(null, null);
            } else {
                // 네트워크 실패나 서버 일시 오류다. 토큰은 멀쩡하므로 지우지
                // 않고 로그인 상태를 유지한다. 재배포 중이거나 오프라인에서
                // 앱을 열었다는 이유로 세션이 사라지면 안 된다.
                // 사용자 정보는 다음에 통신이 되면 채워진다.
                console.warn("인증 확인 실패(일시적일 수 있음), 세션 유지:", error);
                showAppUI({ email: "" }, token);
            }
        }
    } else {
        showAppUI(null, null);
    }

    setupAuthEventListeners();
}

function showAppUI(user, token) {
    const authContainer = document.getElementById("authContainer");
    const appMain = document.getElementById("appMain");
    const userInfo = document.getElementById("userInfo");
    const userEmail = document.getElementById("userEmail");
    const profileImage = document.getElementById("profileImage");
    const profileInitial = document.getElementById("profileInitial");
    const profileMenuBtn = document.getElementById("profileMenuBtn");
    const adminDashboardLink = document.getElementById("adminDashboardLink");
    const brandWordmark = document.getElementById("brandWordmark");
    const headerLoginSlot = document.getElementById("headerLoginSlot");

    // 메인 화면은 로그인 여부와 무관하게 항상 보인다 (기본 오디오북 체험용).
    // 전체를 덮는 auth 카드 대신 헤더의 로그인 버튼으로만 유도한다 —
    // 이전에는 authContainer를 무조건 숨겨서 로그인할 방법이 아예 없었다.
    authContainer.style.display = "none";
    appMain.style.display = "flex";

    const loggedIn = !!(user && token);
    const isAdmin = loggedIn && user.is_admin === true;
    document.body.dataset.isAdmin = String(isAdmin);
    const dropzoneHint = document.querySelector(".dropzone-hint");
    if (dropzoneHint) {
        dropzoneHint.textContent = `지원 파일: DOCX, PDF, TXT, MD, HWP (최대 ${isAdmin ? 50 : 10}MB, 복수 선택 가능)`;
    }
    userInfo.style.display = loggedIn ? "flex" : "none";
    if (headerLoginSlot) headerLoginSlot.style.display = loggedIn ? "none" : "flex";
    if (adminDashboardLink) adminDashboardLink.hidden = !isAdmin;
    if (brandWordmark) brandWordmark.dataset.admin = String(isAdmin);
    if (loggedIn) {
        const profileName = user.full_name || user.email || "사용자";
        userEmail.textContent = user.email || "";
        profileInitial.textContent = profileName.trim().split(/\s+/)[0].slice(0, 2);
        profileMenuBtn.setAttribute("aria-label", `${profileName} 계정 메뉴`);
        profileImage.hidden = true;
        profileImage.removeAttribute("src");
    } else {
        // 비로그인일 때만 구글 버튼을 그린다
        setupSocialLogin();
    }

    updateGenerateHint();
}

/**
 * 토큰이 실제로 무효한지(401/403) 여부를 호출자가 구분할 수 있도록
 * authFailed 플래그를 실어 던진다. 네트워크 실패나 5xx까지 로그아웃으로
 * 취급하면 재배포 중이거나 전파가 끊긴 순간에 앱을 열었다는 이유만으로
 * 세션이 사라진다.
 */
async function fetchCurrentUser(token) {
    const response = await fetch("/api/auth/me", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    if (!response.ok) {
        const err = new Error(`Failed to fetch user (${response.status})`);
        err.authFailed = response.status === 401 || response.status === 403;
        throw err;
    }

    return await response.json();
}

/**
 * 이 기기에 저장된 오디오북을 지운다. 기본 제공 오디오북(isDefault)만 남기고,
 * 그 재생 위치도 초기화한다 — 공용 기기에서 이전 사용자의 흔적이 남지 않게.
 * 로그아웃 정리 트랜잭션을 완료한 뒤 연결을 닫기 위해 별도 연결을 연다.
 */
function clearDeviceAudiobooks() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open("AudiobookMakerDB", 1);
        req.onerror = () => reject(req.error);
        req.onsuccess = () => {
            const database = req.result;
            if (!database.objectStoreNames.contains("audiobooks")) {
                database.close();
                resolve(0);
                return;
            }
            const tx = database.transaction(["audiobooks"], "readwrite");
            const store = tx.objectStore("audiobooks");
            let removed = 0;

            store.openCursor().onsuccess = (e) => {
                const cursor = e.target.result;
                if (!cursor) return;
                if (cursor.value.isDefault) {
                    if (cursor.value.lastPosition) {
                        cursor.update({ ...cursor.value, lastPosition: 0 });
                    }
                } else {
                    cursor.delete();
                    removed++;
                }
                cursor.continue();
            };

            tx.oncomplete = () => { database.close(); resolve(removed); };
            tx.onerror = () => { database.close(); reject(tx.error); };
        };
    });
}

async function logout() {
    // 기기 데이터를 지우는 동작이라 반드시 확인을 받는다.
    const confirmed = window.confirm(
        "로그아웃하면 이 기기에 저장된 오디오북이 모두 삭제됩니다.\n" +
        "기본 제공 오디오북만 남습니다.\n\n" +
        "삭제 전에 클라우드로 백업하며, 다시 로그인하면 복원됩니다.\n\n" +
        "계속하시겠습니까?"
    );
    if (!confirmed) return;

    const loadingOverlay = document.getElementById("loadingOverlay");
    if (loadingOverlay) {
        const h3 = loadingOverlay.querySelector("h3");
        const p = loadingOverlay.querySelector("p");
        const status = loadingOverlay.querySelector(".loading-status");
        const progress = loadingOverlay.querySelector(".progress-container");

        if (h3) h3.textContent = "로그아웃 처리 중...";
        if (p) p.textContent = "클라우드에 데이터를 동기화하고 기기를 정리하고 있습니다.";
        if (status) status.style.display = "none";
        if (progress) progress.style.display = "none";

        loadingOverlay.classList.add("show");
    }

    // 지우기 전에 아직 안 올라간 것을 먼저 올린다. 이 단계를 건너뛰면
    // 복구할 방법이 없다 — 이전 구현은 경고만 하고 실제로 막지 못했다.
    if (window.__syncAudiobooksToCloud) {
        let result;
        try {
            result = await window.__syncAudiobooksToCloud();
        } catch (error) {
            console.error("로그아웃 전 백업 실패:", error);
            result = { ok: false, failed: -1 };
        }
        if (!result.ok) {
            const proceed = window.confirm(
                "클라우드 백업에 실패했습니다.\n" +
                "지금 로그아웃하면 백업되지 않은 오디오북은 복구할 수 없습니다.\n\n" +
                "그래도 로그아웃할까요?\n" +
                "(취소를 누르고 잠시 후 다시 시도하는 것을 권합니다)"
            );
            if (!proceed) {
                if (loadingOverlay) loadingOverlay.classList.remove("show");
                return;
            }
        }
    }

    try {
        await clearDeviceAudiobooks();
    } catch (error) {
        if (loadingOverlay) loadingOverlay.classList.remove("show");
        // 삭제에 실패했는데 로그아웃만 되면 데이터가 남은 채 방치된다.
        console.error("기기 데이터 삭제 실패:", error);
        window.alert("기기 데이터를 삭제하지 못했습니다. 로그아웃을 취소합니다.");
        return;
    }

    // 재생 설정 등 사용자 흔적도 함께 정리한다
    localStorage.removeItem("authToken");
    localStorage.removeItem("textAudio_playbackSpeed");
    localStorage.removeItem("textAudio_repeatMode");
    location.reload();
}

function setupAuthEventListeners() {
    const logoutBtn = document.getElementById("logoutBtn");
    const userInfo = document.getElementById("userInfo");
    const profileMenuBtn = document.getElementById("profileMenuBtn");
    const profileMenu = document.getElementById("profileMenu");
    const brandWordmark = document.getElementById("brandWordmark");
    let logoTapCount = 0;
    let logoTapTimer;

    function closeProfileMenu() {
        profileMenu.hidden = true;
        profileMenuBtn.setAttribute("aria-expanded", "false");
    }

    // 로그인 버튼은 구글이 직접 그리고 클릭도 구글이 처리한다.
    // 우리가 붙일 핸들러가 없다 — setupSocialLogin()이 렌더만 담당한다.
    if (logoutBtn) {
        logoutBtn.addEventListener("click", logout);
    }
    if (profileMenuBtn && profileMenu && userInfo) {
        profileMenuBtn.addEventListener("click", () => {
            const isOpen = !profileMenu.hidden;
            profileMenu.hidden = isOpen;
            profileMenuBtn.setAttribute("aria-expanded", String(!isOpen));
        });
        document.addEventListener("click", (event) => {
            if (!userInfo.contains(event.target)) closeProfileMenu();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeProfileMenu();
        });
    }
    if (brandWordmark) {
        brandWordmark.addEventListener("click", () => {
            if (brandWordmark.dataset.admin !== "true") return;
            logoTapCount += 1;
            clearTimeout(logoTapTimer);
            logoTapTimer = setTimeout(() => { logoTapCount = 0; }, 700);
            if (logoTapCount === 3) window.location.assign("/admin");
        });
    }
}

// ============================================================
// Google OAuth Handler
// ============================================================

/** GSI 스크립트는 async defer로 로드되므로 준비될 때까지 기다린다. */
function waitForGoogleSdk(timeoutMs = 8000) {
    return new Promise((resolve) => {
        const start = Date.now();
        (function check() {
            if (window.google && google.accounts && google.accounts.id) return resolve(true);
            if (Date.now() - start > timeoutMs) return resolve(false);
            setTimeout(check, 100);
        })();
    });
}

/**
 * 소셜 로그인 제공자 정의.
 *
 * 카카오/네이버/애플을 추가할 때 손댈 곳은 여기 하나다. 각 제공자는
 * render(slot, clientId)만 구현하면 되고, 인증에 성공하면 공통 함수인
 * completeSocialLogin(provider, token)을 부르면 된다.
 *
 * 서버도 대칭이다 — /api/auth/social/{provider} 하나로 받는다.
 */
const SOCIAL_PROVIDERS = {
    google: {
        // GSI는 팝업을 프로그램으로 열 수 없다. 구글이 직접 그린 버튼을
        // 눌러야만 열리므로 공식 버튼을 그대로 노출한다.
        // One Tap(prompt)은 쓰지 않는다 — 팝업 방식으로 통일한다.
        initialized: false,
        async render(slot, clientId) {
            if (!(await waitForGoogleSdk())) {
                throw new Error("Google 로그인 스크립트를 불러오지 못했습니다.");
            }
            if (!this.initialized) {
                google.accounts.id.initialize({
                    client_id: clientId,
                    callback: (res) => completeSocialLogin("google", res.credential),
                    ux_mode: "popup"
                });
                this.initialized = true;
            }
            slot.innerHTML = "";
            google.accounts.id.renderButton(slot, {
                type: "standard",
                theme: "outline",
                size: "large",
                shape: "pill",
                text: "signin_with"
            });
        }
    }

    // kakao: { async render(slot, jsKey) { ... completeSocialLogin("kakao", token) } },
    // naver: { ... },
    // apple: { ... },
};

/** 제공자별 버튼을 지정된 슬롯들에 그린다. */
async function setupSocialLogin() {
    const slots = ["headerGoogleBtn", "googleLoginBtn"]
        .map(id => document.getElementById(id))
        .filter(Boolean);
    if (slots.length === 0) return;

    try {
        // 클라이언트 ID는 서버에서 받아온다. 코드에 박아두면 환경마다 달라질
        // 수 없고, 실제로 플레이스홀더가 남아 로그인이 동작하지 않았다.
        const config = await fetch("/api/config").then(r => r.json());
        const providers = config.providers || {};
        const enabled = Object.keys(providers).filter(p => SOCIAL_PROVIDERS[p]);

        if (enabled.length === 0) {
            showAuthError("로그인 설정이 준비되지 않았습니다. 관리자에게 문의해 주세요.");
            return;
        }

        for (const name of enabled) {
            for (const slot of slots) {
                try {
                    await SOCIAL_PROVIDERS[name].render(slot, providers[name]);
                } catch (e) {
                    console.error(`${name} 로그인 버튼 렌더 실패:`, e);
                    showAuthError(e.message || "로그인을 준비하지 못했습니다.");
                }
            }
        }
    } catch (error) {
        console.error("Social login setup failed:", error);
        showAuthError("로그인을 준비하지 못했습니다.");
    }
}

/** 제공자가 발급한 토큰을 서버에 넘겨 우리 세션을 만든다. 제공자 공통 경로. */
async function completeSocialLogin(provider, token) {
    const loadingOverlay = document.getElementById("loadingOverlay");
    if (loadingOverlay) {
        const h3 = loadingOverlay.querySelector("h3");
        const p = loadingOverlay.querySelector("p");
        const status = loadingOverlay.querySelector(".loading-status");
        const progress = loadingOverlay.querySelector(".progress-container");

        if (h3) h3.textContent = "로그인 처리 중...";
        if (p) p.textContent = "사용자 정보를 확인하고 있습니다.";
        if (status) status.style.display = "none";
        if (progress) progress.style.display = "none";

        loadingOverlay.classList.add("show");
    }

    try {
        const res = await fetch(`/api/auth/social/${provider}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "로그인 실패");

        localStorage.setItem("authToken", data.access_token);
        setTimeout(() => location.reload(), 500);
    } catch (error) {
        if (loadingOverlay) loadingOverlay.classList.remove("show");
        console.error("Auth error:", error);
        showAuthError(error.message || "로그인에 실패했습니다.");
    }
}



function showAuthError(message) {
    const authMessage = document.getElementById("authMessage");
    // 버튼은 구글이 그린 것이라 여기서 건드리면 지워진다. 메시지만 표시한다.
    if (authMessage) {
        authMessage.textContent = message;
        authMessage.classList.add("error");
    }
}
