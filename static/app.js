function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function getAudiobookDisplayTitle(title) {
    return String(title).replace(/\.[^/.]+$/, "");
}

function syncUrlClearButton(input, button) {
    button.hidden = input.value.length === 0;
}


document.addEventListener("DOMContentLoaded", async () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Check authentication status
    await initializeAuth();

    // DOM Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const fileDetails = document.getElementById("fileDetails");
    const fileName = document.getElementById("fileName");
    const fileSize = document.getElementById("fileSize");
    const removeFileBtn = document.getElementById("removeFileBtn"); // may be null if UI simplified
    
    const voiceSelect = document.getElementById("voiceSelect");
    const voiceDesc = document.getElementById("voiceDesc");
    const speedSlider = document.getElementById("speedSlider");
    const speedVal = document.getElementById("speedVal");
    const pitchSlider = document.getElementById("pitchSlider");
    const pitchVal = document.getElementById("pitchVal");
    
    const generateBtn = document.getElementById("generateBtn");
    const previewPlaceholder = document.getElementById("previewPlaceholder"); // may be null if UI simplified
    const previewText = document.getElementById("previewText");
    const charCountBadge = document.getElementById("charCountBadge");
    
    const libraryEmpty = document.getElementById("libraryEmpty");
    const audioList = document.getElementById("audioList");
    const importLinkBtn = document.getElementById("importLinkBtn");
    const appVersionDisplay = document.getElementById("appVersionDisplay");
    
    // Generation Modal
    const generationModal = document.getElementById("generationModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const modalFocusOrigins = new WeakMap();

    function rememberModalFocus(backdropElement, focusElement) {
        modalFocusOrigins.set(backdropElement, document.activeElement);
        requestAnimationFrame(() => focusElement?.focus());
    }

    function restoreModalFocus(backdropElement) {
        const focusOrigin = modalFocusOrigins.get(backdropElement);
        if (focusOrigin instanceof HTMLElement && document.contains(focusOrigin)) {
            focusOrigin.focus();
        }
    }

    function openGenerationModal() {
        generationModal.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(generationModal, closeModalBtn);
    }

    function closeGenerationModal() {
        generationModal.classList.remove("show");
        document.body.style.overflow = "";
        stopVoicePreview();
        restoreModalFocus(generationModal);
    }
    
    const loadingOverlay = document.getElementById("loadingOverlay");
    
    const toast = document.getElementById("toast");
    const toastIcon = document.getElementById("toastIcon");
    const toastMessage = document.getElementById("toastMessage");
    
    // Synced Reader DOM Elements
    const readerOverlay = document.getElementById("readerOverlay");
    const readerBookTitle = document.getElementById("readerBookTitle");
    const readerShareBtn = document.getElementById("readerShareBtn");
    const closeReaderBtn = document.getElementById("closeReaderBtn");
    const readerContent = document.getElementById("readerContent");
    const readerAudio = document.getElementById("readerAudio");
    const readerPlayPauseBtn = document.getElementById("readerPlayPauseBtn");
    const playIconSvg = document.getElementById("playIconSvg");
    const pauseIconSvg = document.getElementById("pauseIconSvg");
    const readerCurrentTime = document.getElementById("readerCurrentTime");
    const readerDuration = document.getElementById("readerDuration");
    const readerProgressBar = document.getElementById("readerProgressBar");
    const readerProgressFill = document.getElementById("readerProgressFill");
    const readerContainer = readerOverlay.querySelector(".reader-container");

    // Play/Pause icon toggle helpers (no innerHTML, no lucide.createIcons)
    function showPlayIcon() {
        if (playIconSvg) playIconSvg.style.display = "";
        if (pauseIconSvg) pauseIconSvg.style.display = "none";
    }
    function showPauseIcon() {
        if (playIconSvg) playIconSvg.style.display = "none";
        if (pauseIconSvg) pauseIconSvg.style.display = "";
    }

    // Reader Mode UI Interaction State
    let readerUiTimeout = null;
    let lastScrollTop = 0;
    let isAutoScrolling = false;
    let readerUiProgress = 0;      // 0 = 완전히 펼침, 1 = 완전히 접힘
    let readerSnapTimeout = null;
    const READER_COLLAPSE_DISTANCE = 90;  // 이만큼 스크롤하면 완전히 접힘

    function setReaderUiProgress(p, animated) {
        if (!readerContainer) return;
        readerUiProgress = Math.min(1, Math.max(0, p));
        readerContainer.classList.toggle("ui-snapping", animated === true);
        readerContainer.style.setProperty("--reader-ui-p", readerUiProgress.toFixed(3));
    }

    // 바 높이는 safe-area 때문에 기기마다 달라서 실측해 본문 패딩 기준으로 넘긴다.
    // 펼친 상태(p=0)에서 재야 정확하다.
    function measureReaderBars() {
        if (!readerContainer) return;
        const header = readerContainer.querySelector(".reader-header");
        const controls = readerContainer.querySelector(".reader-controls");
        const secondary = readerContainer.querySelector(".reader-secondary-controls");
        // scrollHeight는 max-height에 눌리지 않는 자연 높이를 준다
        if (secondary) {
            readerContainer.style.setProperty("--reader-secondary-h", secondary.scrollHeight + "px");
        }
        if (header) readerContainer.style.setProperty("--reader-header-h", header.offsetHeight + "px");
        if (controls) readerContainer.style.setProperty("--reader-controls-h", controls.offsetHeight + "px");
    }

    function showReaderUi() {
        setReaderUiProgress(0, true);

        clearTimeout(readerUiTimeout);
        // Auto-hide UI after 4 seconds of inactivity if we are playing
        readerUiTimeout = setTimeout(() => {
            if (!readerAudio.paused) {
                setReaderUiProgress(1, true);
            }
        }, 4000);
    }

    // 리더가 열릴 때만 호출된다 — 펼친 상태를 만든 뒤 바 높이를 실측한다
    function resetReaderUiTimeout() {
        lastScrollTop = 0;
        setReaderUiProgress(0, false);
        requestAnimationFrame(measureReaderBars);
        showReaderUi();
    }
    
    // --- iOS Native Style Swipe-to-Dismiss ---
    function setupSwipeToDismiss(backdropElement, contentElementSelector) {
        if (!backdropElement) return;
        const contentElement = backdropElement.matches(contentElementSelector) 
            ? backdropElement 
            : backdropElement.querySelector(contentElementSelector);
        
        if (!contentElement) return;

        let startY = 0;
        let currentY = 0;
        let isDragging = false;
        let dragStartTime = 0;

        contentElement.addEventListener('touchstart', (e) => {
            const scrollable = e.target.closest('.modal-scroll-area, .index-sheet-list');
            if (scrollable && scrollable.scrollTop > 0) return;
            
            startY = e.touches[0].clientY;
            currentY = startY;
            isDragging = true;
            dragStartTime = Date.now();
            contentElement.classList.add('ui-dragging');
            contentElement.style.transition = 'none';
        }, { passive: true });

        contentElement.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            
            const scrollable = e.target.closest('.modal-scroll-area, .index-sheet-list');
            const y = e.touches[0].clientY;
            const deltaY = y - startY;
            
            if (scrollable) {
                const isAtTop = scrollable.scrollTop <= 0;
                if (!isAtTop || deltaY < 0) {
                    isDragging = false;
                    contentElement.classList.remove('ui-dragging');
                    contentElement.style.transform = '';
                    contentElement.style.transition = '';
                    return;
                }
            }
            
            currentY = y;
            if (deltaY > 0) {
                contentElement.style.transform = `translateY(${deltaY}px)`;
                if (e.cancelable && !scrollable) e.preventDefault();
            } else {
                contentElement.style.transform = `translateY(${deltaY * 0.2}px)`; // rubber band effect
            }
        }, { passive: false });

        contentElement.addEventListener('touchend', (e) => {
            if (!isDragging) return;
            isDragging = false;
            contentElement.classList.remove('ui-dragging');
            contentElement.style.transition = '';

            const deltaY = currentY - startY;
            const dragDuration = Date.now() - dragStartTime;
            const velocity = deltaY / dragDuration;

            const contentHeight = contentElement.offsetHeight;
            const passedThreshold = deltaY > contentHeight * 0.25;
            const isFlick = velocity > 0.6;

            if (deltaY > 0 && (passedThreshold || (isFlick && deltaY > 30))) {
                contentElement.style.transform = '';
                backdropElement.classList.remove('show');
                document.body.style.overflow = '';
            } else {
                contentElement.style.transform = '';
            }
        }, { passive: true });

        // 시스템 제스처 충돌 등으로 touchend 없이 제스처가 강제 종료될 때
        // 온다. 이걸 처리하지 않으면 마지막 러버밴드 위치(예: translateY(-59px))가
        // 인라인 스타일로 그대로 남아, 카드가 화면 하단에 붙지 못하고 그
        // 아래로 배경색 빈 공간이 보이는 상태로 고착된다.
        contentElement.addEventListener('touchcancel', () => {
            if (!isDragging) return;
            isDragging = false;
            contentElement.classList.remove('ui-dragging');
            contentElement.style.transition = '';
            contentElement.style.transform = '';
        }, { passive: true });

        // 이중 안전장치: 여는 지점이 여러 군데라(파일 업로드 후 자동으로,
        // "더보기" 버튼으로, 목차 버튼으로) 그 각각에서 리셋하는 대신
        // "show" 클래스가 다시 붙는 시점 자체를 감지해 한 곳에서 보장한다.
        // touchcancel을 못 잡는 경로가 남아 있어도 다음에 열 때는 항상
        // 깨끗한 상태로 시작한다.
        new MutationObserver(() => {
            if (backdropElement.classList.contains('show')) {
                contentElement.style.transform = '';
                contentElement.style.transition = '';
            }
        }).observe(backdropElement, { attributes: true, attributeFilter: ['class'] });
    }

    setupSwipeToDismiss(generationModal, '.modal-content');
    
    setupSwipeToDismiss(document.getElementById("actionSheetBackdrop"), '.action-sheet');
    setupSwipeToDismiss(document.getElementById("indexSheetBackdrop"), '.index-sheet');
    setupSwipeToDismiss(document.getElementById("loginPromptBackdrop"), '.action-sheet');

    // Close generation modal
    closeModalBtn.addEventListener("click", () => {
        closeGenerationModal();
    });
    
    // Import Shared Link
    if (importLinkBtn) {
        importLinkBtn.addEventListener("click", async () => {
            const url = prompt("공유받은 링크를 붙여넣어 주세요:\n(예: https://.../share/...)");
            if (!url) return;
            
            try {
                const match = url.match(/\/share\/([a-zA-Z0-9-]+)/);
                if (!match) {
                    showToast("유효한 공유 링크가 아닙니다.", "error");
                    return;
                }
                const shareId = match[1];
                
                showToast("공유 링크 정보를 불러오는 중...", "info");
                const response = await fetch(`/api/share/${shareId}`);
                if (!response.ok) {
                    throw new Error("공유 링크가 만료되었거나 존재하지 않습니다.");
                }
                
                const data = await response.json();
                openSharedReaderMode(data.title, data.sentences, data.audio_url, shareId);
            } catch (err) {
                console.error(err);
                showToast(err.message || "공유 링크 불러오기에 실패했습니다.", "error");
            }
        });
    }
    
    // Listen for scroll on the reader content
    readerContent.addEventListener("scroll", () => {
        const currentScrollTop = readerContent.scrollTop;

        // Ignore automated scrolling (e.g. following text)
        if (isAutoScrolling) {
            lastScrollTop = Math.max(0, currentScrollTop);
            return;
        }

        const delta = currentScrollTop - lastScrollTop;
        lastScrollTop = Math.max(0, currentScrollTop);

        if (currentScrollTop <= 0) {
            setReaderUiProgress(0, true);   // 맨 위에서는 항상 펼친다
        } else {
            // 트랜지션 없이 스크롤량에 비례해 손가락을 그대로 따라간다
            setReaderUiProgress(readerUiProgress + delta / READER_COLLAPSE_DISTANCE, false);
            clearTimeout(readerUiTimeout);
        }

        // 스크롤이 멈추면 가까운 쪽으로 스냅해서 어중간한 상태로 남지 않게 한다
        clearTimeout(readerSnapTimeout);
        readerSnapTimeout = setTimeout(() => {
            setReaderUiProgress(readerUiProgress > 0.5 ? 1 : 0, true);
        }, 140);
    }, { passive: true });
    
    // Touch/Click explicitly shows the UI
    readerContent.addEventListener("click", showReaderUi);
    readerContent.addEventListener("touchstart", showReaderUi, { passive: true });

    // 회전하면 safe-area와 바 높이가 달라지므로 본문 패딩 기준을 다시 잡는다
    window.addEventListener("resize", () => {
        if (readerOverlay && readerOverlay.classList.contains("show")) measureReaderBars();
    });

    // App State
    let currentTextId = null;
    let currentTextAccessToken = null;
    let uploadedFile = null;
    let availableVoices = [];
    let db = null;
    let objectUrls = {}; 
    let lastActiveSpan = null;
    let currentReadingAudioId = null;
    let currentAudioObject = null;
    let currentReaderObjectUrl = null; 
    let lastPlaybackSyncTime = 0;
    let lastPositionSaveSecond = -1;

    // Initialize Database and App
    initDB().then(() => {
        loadVoices();
        renderLibrary();
        seedDefaultBookIfNeeded();
        // DB가 열린 뒤에 동기화한다 — 먼저 돌면 db가 null이라 실패한다
        if (isLoggedIn()) syncWithCloud();
    });

    // -------------------------------------------------------
    // 당겨서 새로고침 (iOS 스타일)
    //
    // body가 스크롤 주체다. 목록의 스와이프 삭제는 가로 이동만 처리하므로
    // (|deltaX| > |deltaY| 조건) 세로 당김과는 충돌하지 않는다.
    // -------------------------------------------------------
    const pullEl = document.getElementById("pullRefresh");
    if (pullEl) {
        const PULL_THRESHOLD = 64;   // 이만큼 당기고 놓으면 새로고침
        const PULL_MAX = 110;        // 이 이상은 더 안 내려간다
        const SPOKES = 12;

        let pullStartY = 0;
        let pullDistance = 0;
        let pullActive = false;      // 당김 제스처 추적 중
        let refreshing = false;

        const spokes = [...pullEl.querySelectorAll(".pull-spinner i")];
        // 스피너와 콘텐츠가 같은 값을 읽어야 하므로 공통 조상에 둔다
        const root = document.documentElement;

        function setPull(distance, progress) {
            root.classList.add("pull-active");
            root.style.setProperty("--pull-y", `${distance}px`);
            pullEl.style.opacity = String(Math.min(progress * 1.4, 1));
            // 진행도만큼 스포크를 차례로 켠다
            const lit = Math.round(progress * SPOKES);
            spokes.forEach((s, i) => { s.style.opacity = i < lit ? "1" : "0.15"; });
        }

        function resetPull(animated) {
            const animate = animated !== false;
            pullEl.classList.toggle("settling", animate);
            root.classList.toggle("pull-settling", animate);
            pullEl.classList.remove("refreshing");
            pullDistance = 0;
            root.style.setProperty("--pull-y", "0px");
            pullEl.style.opacity = "0";
            spokes.forEach(s => { s.style.opacity = ""; });

            // 되돌아간 뒤에는 transform을 완전히 걷어낸다. 남겨두면 콘텐츠에
            // 스택 컨텍스트가 계속 붙어 있게 된다.
            const cleanup = () => {
                if (pullActive || refreshing) return;
                root.classList.remove("pull-active", "pull-settling");
                root.style.removeProperty("--pull-y");
                pullEl.classList.remove("settling");
            };
            if (animate) setTimeout(cleanup, 400);
            else cleanup();
        }

        // 다른 화면이 떠 있으면 당김을 잡지 않는다
        function pullBlocked() {
            return refreshing
                || document.getElementById("readerOverlay").classList.contains("show")
                || document.getElementById("generationModal").classList.contains("show")
                || document.getElementById("actionSheetBackdrop").classList.contains("show");
        }

        window.addEventListener("touchstart", (e) => {
            if (pullBlocked() || window.scrollY > 0 || e.touches.length !== 1) return;
            pullStartY = e.touches[0].clientY;
            pullActive = true;
            pullEl.classList.remove("settling");
        }, { passive: true });

        window.addEventListener("touchmove", (e) => {
            if (!pullActive) return;
            const dy = e.touches[0].clientY - pullStartY;

            // 위로 밀거나 스크롤이 시작되면 당김이 아니다
            if (dy <= 0 || window.scrollY > 0) {
                pullActive = false;
                resetPull(true);
                return;
            }

            // 고무줄 저항: 당길수록 덜 따라온다
            pullDistance = Math.min(dy * 0.5, PULL_MAX);
            setPull(pullDistance, Math.min(pullDistance / PULL_THRESHOLD, 1));

            // 네이티브 오버스크롤(고무줄)이 같이 일어나면 어색하므로 막는다
            if (e.cancelable) e.preventDefault();
        }, { passive: false });

        async function runRefresh() {
            refreshing = true;
            pullEl.classList.add("settling", "refreshing");
            root.classList.add("pull-active", "pull-settling");
            // 새로고침 중에는 콘텐츠가 임계 지점에 머물러 스피너 자리를 만든다
            root.style.setProperty("--pull-y", `${PULL_THRESHOLD}px`);
            pullEl.style.opacity = "1";
            spokes.forEach(s => { s.style.opacity = ""; });

            const startedAt = Date.now();
            try {
                if (isLoggedIn()) await syncWithCloud();
                await renderLibrary();
            } catch (err) {
                console.error("새로고침 실패:", err);
            }
            // 너무 빨리 끝나면 깜빡이는 것처럼 보인다. 최소 표시 시간을 준다.
            const elapsed = Date.now() - startedAt;
            if (elapsed < 600) await new Promise(r => setTimeout(r, 600 - elapsed));

            refreshing = false;
            resetPull(true);
        }

        window.addEventListener("touchend", () => {
            if (!pullActive) return;
            pullActive = false;
            if (pullDistance >= PULL_THRESHOLD) {
                runRefresh();
            } else {
                resetPull(true);
            }
        }, { passive: true });

        // 시스템 제스처 등으로 강제 종료되면 원위치로 되돌린다
        window.addEventListener("touchcancel", () => {
            if (!pullActive) return;
            pullActive = false;
            resetPull(true);
        }, { passive: true });
    }

    // -------------------------------------------------------
    // Background → Foreground 복귀 시 배포 업데이트 감지
    // 서버가 재시작(재배포)되면 build_id가 바뀌어 자동 리로드
    // -------------------------------------------------------
    let cachedBuildId = null;

    async function fetchBuildId() {
        try {
            const res = await fetch("/api/version", { cache: "no-store" });
            if (!res.ok) return null;
            const data = await res.json();
            return data.build_id || null;
        } catch (e) {
            return null; // 네트워크 오프라인이면 조용히 무시
        }
    }

    // 최초 로드 시 build_id 기억
    fetchBuildId().then(id => { cachedBuildId = id; });

    let lastVersionCheckTime = 0;

    // 버전 확인 및 업데이트 로직 (공통)
    async function checkAndReloadIfUpdated() {
        if (!cachedBuildId) {
            cachedBuildId = await fetchBuildId();
            return;
        }
        const latestId = await fetchBuildId();
        if (latestId && latestId !== cachedBuildId) {
            // 새 배포 감지 → 토스트 알림 후 3초 뒤 리로드
            showToast("리소스 업데이트 중", "info");
            setTimeout(() => {
                // Service Worker 캐시도 함께 비우고 리로드
                if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
                    caches.keys().then(keys => {
                        Promise.all(keys.map(k => caches.delete(k))).then(() => {
                            window.location.reload();
                        });
                    });
                } else {
                    window.location.reload();
                }
            }, 3000);
        }
    }

    // 앱이 포그라운드로 돌아올 때마다 체크
    document.addEventListener("visibilitychange", async () => {
        if (document.visibilityState !== "visible") return;
        checkAndReloadIfUpdated();
    });

    // 메인 화면에서 스크롤 다운할 때도 버전 확인 (30초마다 한 번)
    const appMain = document.querySelector(".app-main");
    if (appMain) {
        appMain.addEventListener("scroll", () => {
            const now = Date.now();
            if (now - lastVersionCheckTime > 30000) { // 30초 이상 지났으면 확인
                lastVersionCheckTime = now;
                checkAndReloadIfUpdated();
            }
        }, { passive: true });
    }

    // Mobile specific UI adjustments
    const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;
    if (isMobileDevice) {
        const dropzoneText = document.querySelector(".dropzone-text");
        if (dropzoneText) {
            dropzoneText.textContent = "이곳을 터치하여 문서를 업로드하세요";
        }
        const dropzoneHint = document.querySelector(".dropzone-hint");
        if (dropzoneHint) {
            dropzoneHint.textContent = "지원: DOCX, PDF, TXT, MD, HWP";
        }
    }

    // Voice Selection Change Handler
    voiceSelect.addEventListener("change", (e) => {
        const selectedVoiceShortName = e.target.value;
        updateVoiceDescription(selectedVoiceShortName);
        stopVoicePreview();
    });

    // --- 목소리 미리듣기 ---
    const voicePreviewBtn = document.getElementById("voicePreviewBtn");
    const voicePreviewLabel = document.getElementById("voicePreviewLabel");
    let previewAudio = null;

    function stopVoicePreview() {
        if (previewAudio) {
            previewAudio.pause();
            previewAudio = null;
        }
        if (voicePreviewBtn) {
            voicePreviewBtn.disabled = false;
            if (voicePreviewLabel) voicePreviewLabel.textContent = "미리듣기";
        }
    }

    if (voicePreviewBtn) {
        voicePreviewBtn.addEventListener("click", async () => {
            // 재생 중이면 정지 토글
            if (previewAudio) {
                stopVoicePreview();
                return;
            }
            const voice = voiceSelect.value;
            if (!voice) return;

            voicePreviewBtn.disabled = true;
            if (voicePreviewLabel) voicePreviewLabel.textContent = "준비 중...";
            try {
                // 서버가 처음 한 번만 합성하고 이후로는 캐시를 준다
                const res = await fetch(`/api/voices/${encodeURIComponent(voice)}/preview`);
                if (!res.ok) throw new Error("미리듣기를 불러오지 못했습니다.");
                const blob = await res.blob();

                previewAudio = new Audio(URL.createObjectURL(blob));
                previewAudio.onended = stopVoicePreview;
                previewAudio.onerror = () => {
                    stopVoicePreview();
                    showToast("미리듣기를 재생하지 못했습니다.", "error");
                };
                voicePreviewBtn.disabled = false;
                if (voicePreviewLabel) voicePreviewLabel.textContent = "정지";
                await previewAudio.play();
            } catch (error) {
                console.error(error);
                stopVoicePreview();
                showToast(error.message || "미리듣기에 실패했습니다.", "error");
            }
        });
    }

    function updateVoiceDescription(shortName) {
        const voiceObj = availableVoices.find(v => v.short_name === shortName);
        if (voiceObj) {
            voiceDesc.textContent = voiceObj.description || "선택한 음성의 상세 특징이 표시됩니다.";
            voiceDesc.style.opacity = 1;
        } else {
            voiceDesc.textContent = "선택한 음성의 상세 특징이 표시됩니다.";
        }
    }

    // ----------------------------------------------------
    // 0. IndexedDB Utility Module (Browser Local Storage)
    // ----------------------------------------------------
    function initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open("AudiobookMakerDB", 1);
            
            request.onerror = (event) => {
                console.error("Database error: ", event.target.error);
                showToast("DB를 열 수 없습니다.", "error");
                reject(event.target.error);
            };
            
            request.onsuccess = (event) => {
                db = event.target.result;
                resolve(db);
            };
            
            request.onupgradeneeded = (event) => {
                const dbInstance = event.target.result;
                if (!dbInstance.objectStoreNames.contains("audiobooks")) {
                    dbInstance.createObjectStore("audiobooks", { keyPath: "id" });
                }
            };
        });
    }

    function saveAudiobookToDB(entry) {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(["audiobooks"], "readwrite");
            const store = transaction.objectStore("audiobooks");
            const request = store.put(entry);
            
            request.onsuccess = () => resolve();
            request.onerror = (e) => reject(e.target.error);
        });
    }

    function getAllAudiobooksFromDB() {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(["audiobooks"], "readonly");
            const store = transaction.objectStore("audiobooks");
            const request = store.getAll();
            
            request.onsuccess = (e) => {
                const list = e.target.result || [];
                // 기본 제공 오디오북은 항상 최상단에 고정
                list.sort((a, b) => {
                    if (!!a.isDefault !== !!b.isDefault) return a.isDefault ? -1 : 1;
                    return b.timestamp - a.timestamp;
                });
                resolve(list);
            };
            request.onerror = (e) => reject(e.target.error);
        });
    }

    function deleteAudiobookFromDB(id) {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(["audiobooks"], "readwrite");
            const store = transaction.objectStore("audiobooks");
            const request = store.delete(id);
            
            request.onsuccess = () => resolve();
            request.onerror = (e) => reject(e.target.error);
        });
    }

    function updateAudiobookPosition(id, lastPosition) {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(["audiobooks"], "readwrite");
            const store = transaction.objectStore("audiobooks");
            const request = store.get(id);
            
            request.onsuccess = (e) => {
                const data = e.target.result;
                if (data) {
                    data.lastPosition = lastPosition;
                    data.playbackUpdatedAt = Date.now();
                    store.put(data);
                }
                resolve(data);
            };
            request.onerror = (e) => reject(e.target.error);
        });
    }

    // ----------------------------------------------------
    // Fetch and display Service Worker version
    // Display app version from sw.js CACHE_NAME
    if (appVersionDisplay) {
        fetch("/sw.js", { cache: "no-store" })
            .then(res => res.text())
            .then(text => {
                const match = text.match(/CACHE_NAME\s*=\s*["']([^"']+)["']/);
                if (match && match[1]) {
                    appVersionDisplay.textContent = `v ${match[1]}`;
                } else {
                    console.warn("Could not find CACHE_NAME in sw.js");
                }
            })
            .catch(err => console.error("Failed to fetch sw version:", err));
    } else {
        console.warn("appVersionDisplay element not found");
    }

    // ----------------------------------------------------
    // 1. API Call: Load Voices
    // ----------------------------------------------------
    async function loadVoices() {
        try {
            const response = await fetch("/api/voices");
            if (!response.ok) throw new Error("목소리 목록을 불러오지 못했습니다.");
            const voices = await response.json();
            availableVoices = voices;
            
            voiceSelect.innerHTML = "";
            
            if (voices.length === 0) {
                voiceSelect.innerHTML = '<option value="ko-KR-SunHiNeural">선희 (차분한 뉴스/정보 전달 - 여성)</option>';
                return;
            }
            
            voices.forEach(voice => {
                const option = document.createElement("option");
                option.value = voice.short_name;
                
                const flag = voice.locale.startsWith("ko-KR") ? "🇰🇷" : "🇺🇸";
                let displayName = voice.friendly_name;
                
                option.textContent = `${flag} ${displayName}`;
                voiceSelect.appendChild(option);
            });

            // 서버가 SUPPORTED_VOICES 순서로 내려주고 첫 번째가 기본값이다
            voiceSelect.selectedIndex = 0;

            updateVoiceDescription(voiceSelect.value);

        } catch (error) {
            console.error(error);
            showToast("음성 목록을 가져오지 못했습니다. 기본 설정을 사용합니다.", "error");
            availableVoices = [
                {"short_name": "ko-KR-SunHiNeural", "friendly_name": "선희 (차분한 뉴스/정보 전달 - 여성)", "locale": "ko-KR", "description": "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다."},
                {"short_name": "ko-KR-InJoonNeural", "friendly_name": "인준 (신뢰감 있는 소설/다큐 - 남성)", "locale": "ko-KR", "description": "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다."},
                {"short_name": "ko-KR-JiMinNeural", "friendly_name": "지민 (밝고 상냥한 동화/안내 - 여성)", "locale": "ko-KR", "description": "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다."}
            ];
            voiceSelect.innerHTML = `
                <option value="ko-KR-SunHiNeural" selected>🇰🇷 선희 (차분한 뉴스/정보 전달 - 여성)</option>
                <option value="ko-KR-InJoonNeural">🇰🇷 인준 (신뢰감 있는 소설/다큐 - 남성)</option>
                <option value="ko-KR-JiMinNeural">🇰🇷 지민 (밝고 상냥한 동화/안내 - 여성)</option>
            `;
            updateVoiceDescription(voiceSelect.value);
        }
    }

    // ----------------------------------------------------
    // 2. Drag & Drop / File Input Handlers
    // ----------------------------------------------------
    const openFileInput = () => {
        console.log("🔓 Opening file input...");
        fileInput.click();
    };

    dropzone.addEventListener("click", openFileInput);
    dropzone.addEventListener("touchend", (e) => {
        e.preventDefault();
        console.log("📱 Touch event detected");
        openFileInput();
    });
    
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleBatchFileSelect(e.target.files);
        }
    });

    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add("dragover");
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove("dragover");
        }, false);
    });

    dropzone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleBatchFileSelect(files);
        }
    });

    async function handleBatchFileSelect(files) {

        const validFiles = [];
        for (let file of files) {
            if (file.size > 10 * 1024 * 1024) {
                showToast(`${file.name}: 파일이 너무 큽니다 (최대 10MB)`, "error");
                continue;
            }
            validFiles.push(file);
        }

        if (validFiles.length === 0) return;

        if (validFiles.length === 1) {
            handleFileSelect(validFiles[0]);
        } else {
            processBatchFiles(validFiles);
        }
    }

    // 동시에 처리할 파일 수. 서버가 오디오를 디스크로 내리므로 파일 수만큼
    // RAM이 늘지 않고, TTS 동시 연결은 서버 세마포어가 따로 묶는다.
    const BATCH_CONCURRENCY = 8;

    // 배치는 현재 음성 설정을 모든 파일에 공통 적용하고, 파일마다
    // 추출 → 생성까지 끝낸다. 진행 상황은 라이브러리의 파일별 진행 아이템으로 보여준다.
    async function processBatchFiles(files) {
        const voice = voiceSelect.value;
        const rate = getFormattedSpeed(parseInt(speedSlider.value));
        const pitch = getFormattedPitch(parseInt(pitchSlider.value));

        const totalFiles = files.length;
        let completed = 0;

        showToast(`${totalFiles}개 파일 배치 변환 시작`, "info");

        // 워커들이 큐에서 하나씩 꺼내 처리한다. 동시 실행 수를 제한하는 이유는
        // 서버가 파일 하나를 이미 청크 단위로 병렬 합성하기 때문이다 —
        // 파일까지 무제한 병렬로 돌리면 Edge-TTS 동시 연결이 곱으로 늘어난다.
        const queue = files.slice();

        async function worker() {
            while (queue.length > 0) {
                const file = queue.shift();
                try {
                    const data = await extractText(file);
                    const ok = await generateAudiobook({
                        textId: data.text_id,
                        textAccessToken: data.text_access_token,
                        filename: toAudioFilename(file.name),
                        charCount: data.char_count,
                        voice,
                        rate,
                        pitch
                    });
                    if (ok) completed++;
                } catch (error) {
                    console.error(`파일 처리 실패: ${file.name}`, error);
                    showToast(`${file.name} 처리 실패`, "error");
                }
            }
        }

        const workerCount = Math.min(BATCH_CONCURRENCY, totalFiles);
        await Promise.all(Array.from({ length: workerCount }, worker));

        showToast(`배치 변환 완료: ${completed}/${totalFiles}`, "success");
        fileInput.value = "";
    }

    async function handleFileSelect(file) {
        if (file.size > 10 * 1024 * 1024) {
            showToast("파일 크기가 너무 큽니다. 최대 10MB까지 지원합니다.", "error");
            return;
        }

        uploadedFile = file;
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatBytes(file.size);
        if (fileDetails) fileDetails.style.display = "block";

        await uploadFile(file);
    }

    if (removeFileBtn) {
        removeFileBtn.addEventListener("click", () => {
            currentTextId = null;
            currentTextAccessToken = null;
            uploadedFile = null;
            fileInput.value = "";
            
            if (fileDetails) fileDetails.style.display = "none";
            dropzone.style.display = "flex";
            
            previewText.textContent = "";
            previewText.style.display = "none";
            if (previewPlaceholder) previewPlaceholder.style.display = "flex";
            
            charCountBadge.style.display = "none";
            charCountBadge.textContent = "0 자";
            
            generateBtn.disabled = true;
        });
    }

    // Upload to Server for High-Speed Parsing
    // 텍스트 추출만 수행한다. UI를 건드리지 않아 배치 경로에서 재사용 가능하다.
    async function extractText(file) {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch("/api/upload", {
            method: "POST",
            headers: authHeaders(),
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "텍스트 추출 실패");
        }

        return await response.json();
    }

    // 업로드/URL 가져오기 둘 다 { text_id, filename, char_count, preview } 형태를
    // 돌려주므로, 미리보기 렌더링과 모달 열기는 공통으로 뺀다.
    function applyExtractedText(data) {
        currentTextId = data.text_id;
        currentTextAccessToken = data.text_access_token;
        uploadedFile = { name: data.filename };

        if (previewPlaceholder) previewPlaceholder.style.display = "none";
        previewText.style.display = "block";
        previewText.textContent = data.preview;
        charCountBadge.textContent = `${data.char_count.toLocaleString()} 자`;
        charCountBadge.style.display = "block";

        generateBtn.disabled = false;
        updateGenerateHint();

        setTimeout(() => {
            openGenerationModal();
        }, 50);
    }

    async function uploadFile(file) {
        const dzNormal = document.getElementById("dropzoneNormal");
        const dzLoading = document.getElementById("dropzoneLoading");

        if (dzNormal) dzNormal.style.display = "none";
        if (dzLoading) dzLoading.style.display = "block";

        try {
            const data = await extractText(file);
            applyExtractedText(data);

            // Restore dropzone state
            if (dzNormal) dzNormal.style.display = "block";
            if (dzLoading) dzLoading.style.display = "none";
        } catch (error) {
            console.error(error);
            showToast(error.message, "error");
            if (removeFileBtn) removeFileBtn.click();

            // Restore dropzone state on error
            if (dzNormal) dzNormal.style.display = "block";
            if (dzLoading) dzLoading.style.display = "none";
        }
    }

    // ----------------------------------------------------
    // URL에서 기사 가져오기 (뉴스/커뮤니티 링크)
    //
    // 파일 업로드와 달리 서버가 이 요청에 로그인을 요구한다(SSRF/오픈 프록시
    // 남용 방지). 그래서 요청 전에 먼저 로그인 여부를 확인해, 401을 받고
    // 나서야 알리는 대신 미리 안내한다.
    // ----------------------------------------------------
    const urlInput = document.getElementById("urlInput");
    const urlFetchBtn = document.getElementById("urlFetchBtn");
    const urlClearBtn = document.getElementById("urlClearBtn");

    async function extractTextFromUrl(url) {
        const response = await fetch("/api/extract-url", {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "링크에서 텍스트를 가져오지 못했습니다.");
        }
        return data;
    }

    if (urlFetchBtn) {
        urlFetchBtn.addEventListener("click", async () => {
            const url = (urlInput.value || "").trim();
            if (!url) return;

            if (!isLoggedIn()) {
                showToast("링크 가져오기는 로그인 후 이용할 수 있습니다.", "info");
                const loginSlot = document.getElementById("headerLoginSlot");
                if (loginSlot) loginSlot.scrollIntoView({ behavior: "smooth", block: "center" });
                return;
            }

            urlFetchBtn.disabled = true;
            urlFetchBtn.classList.add("is-loading");
            const originalLabel = urlFetchBtn.querySelector("span");
            const originalText = originalLabel ? originalLabel.textContent : "";
            if (originalLabel) originalLabel.textContent = "가져오는 중...";

            try {
                const data = await extractTextFromUrl(url);
                applyExtractedText(data);
                urlInput.value = "";
                syncUrlClearButton(urlInput, urlClearBtn);
            } catch (error) {
                console.error(error);
                showToast(error.message, "error");
            } finally {
                urlFetchBtn.disabled = false;
                urlFetchBtn.classList.remove("is-loading");
                if (originalLabel) originalLabel.textContent = originalText;
            }
        });
    }

    if (urlInput) {
        urlInput.addEventListener("input", () => syncUrlClearButton(urlInput, urlClearBtn));
        urlInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                urlFetchBtn.click();
            }
        });
    }

    if (urlClearBtn) {
        urlClearBtn.addEventListener("click", () => {
            urlInput.value = "";
            syncUrlClearButton(urlInput, urlClearBtn);
            urlInput.focus();
        });
    }

    document.addEventListener("pointerdown", (event) => {
        if (document.activeElement === urlInput && !event.target.closest(".url-input-row")) {
            urlInput.blur();
        }
    });

    // ----------------------------------------------------
    // 3. Settings Sliders UX
    // ----------------------------------------------------
    speedSlider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        let text = "";
        if (val === 0) text = "보통 (1.0x)";
        else if (val > 0) text = `빠름 (1.${val / 5}x)`;
        else text = `느림 (0.${100 + val * 2}x)`;
        speedVal.textContent = text;
    });

    pitchSlider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        let text = "";
        if (val === 0) text = "기본 (0Hz)";
        else if (val > 0) text = `높음 (+${val}Hz)`;
        else text = `낮음 (${val}Hz)`;
        pitchVal.textContent = text;
    });

    function getFormattedSpeed(val) {
        return val >= 0 ? `+${val}%` : `${val}%`;
    }

    function getFormattedPitch(val) {
        return val >= 0 ? `+${val}Hz` : `${val}Hz`;
    }

    // ----------------------------------------------------
    // 4. Generate Audiobook Action (Stateless Streaming)
    // ----------------------------------------------------
    generateBtn.addEventListener("click", async () => {
        if (!currentTextId) return;

        if (!isLoggedIn()) {
            openLoginPromptSheet();
            return;
        }

        closeGenerationModal();

        const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
        await generateAudiobook({
            textId: currentTextId,
            textAccessToken: currentTextAccessToken,
            filename: toAudioFilename(originalName),
            charCount: parseInt(charCountBadge.textContent.replace(/[^0-9]/g, "")) || 0,
            voice: voiceSelect.value,
            rate: getFormattedSpeed(parseInt(speedSlider.value)),
            pitch: getFormattedPitch(parseInt(pitchSlider.value))
        });
    });

    function toAudioFilename(originalName) {
        const dot = originalName.lastIndexOf('.');
        const base = dot > 0 ? originalName.substring(0, dot) : originalName;
        return base + ".mp3";
    }

    // 오디오북 생성 + 저장. 단일 파일 경로와 배치 경로가 공유한다.
    // 전역 상태 대신 인자만 사용하므로 루프에서 반복 호출해도 안전하다.
    // 성공하면 true, 실패하면 false를 반환한다.
    async function generateAudiobook({ textId, textAccessToken, filename, charCount, voice, rate, pitch }) {
        const audioFilename = filename;
        const safeAudioFilename = escapeHtml(getAudiobookDisplayTitle(audioFilename));

        // 라이브러리 섹션에 인라인 진행 아이템 추가
        libraryEmpty.style.display = "none";
        const progressItem = document.createElement("div");
        progressItem.className = "audio-item audio-item-generating";
        progressItem.innerHTML = `
            <div class="audio-title-group">
                <div class="generating-spinner"></div>
                <div class="generating-info">
                    <span class="audio-title">${safeAudioFilename}</span>
                    <div class="generating-progress-track">
                        <div class="generating-progress-fill" style="width: 0%"></div>
                    </div>
                    <span class="generating-status">오디오북 생성 중...</span>
                </div>
            </div>
        `;
        audioList.prepend(progressItem);

        // 라이브러리 섹션으로 스크롤
        setTimeout(() => {
            document.querySelector(".library-section").scrollIntoView({ behavior: "smooth" });
        }, 200);

        const inlineFill = progressItem.querySelector(".generating-progress-fill");
        const inlineStatus = progressItem.querySelector(".generating-status");

        try {
            trackProductEvent("generation_started");
            const formData = new FormData();
            formData.append("text_id", textId);
            formData.append("text_access_token", textAccessToken);
            formData.append("voice", voice);
            formData.append("rate", rate);
            formData.append("pitch", pitch);

            // 1. Request Job ID from server (Returns immediately)
            const response = await fetch("/api/synthesize", {
                method: "POST",
                headers: authHeaders(),
                body: formData
            });

            if (!response.ok) {
                throw new Error("오디오북 변환 요청 실패. 서버 연결을 확인하세요.");
            }

            const resData = await response.json();
            const jobId = resData.job_id;
            
            // 2. Poll job status until completed
            const pollJobStatus = async (id) => {
                const pollRes = await fetch(`/api/job/${id}`, { headers: authHeaders() });
                if (!pollRes.ok) throw new Error("작업 상태 통신 실패");
                
                const jobData = await pollRes.json();
                
                if (jobData.status === "processing") {
                    const completedChunks = Number(jobData.completed_chunks) || 0;
                    const totalChunks = Number(jobData.total_chunks) || 0;
                    if (totalChunks > 0) {
                        const progress = Math.round((completedChunks / totalChunks) * 100);
                        inlineFill.style.width = `${Math.min(progress, 100)}%`;
                        inlineStatus.textContent = `음성 변환 중... (${completedChunks}/${totalChunks})`;
                    } else {
                        inlineStatus.textContent = "음성 변환 준비 중...";
                    }
                    // Wait 2 seconds and check again
                    return new Promise(resolve => {
                        setTimeout(() => resolve(pollJobStatus(id)), 2000);
                    });
                } else if (jobData.status === "completed") {
                    return jobData;
                } else if (jobData.status === "error") {
                    throw new Error(jobData.error || "서버 오디오 변환 에러 발생");
                } else {
                    throw new Error("알 수 없는 작업 상태입니다.");
                }
            };
            
            const completedJobData = await pollJobStatus(jobId);

            const sentences = completedJobData.sentences;

            // 오디오는 별도 엔드포인트에서 바이너리로 받는다. 서버가 base64로
            // 메모리에 들고 있지 않으므로 동시 처리 수를 늘려도 안전하다.
            const audioRes = await fetch(completedJobData.audio_url, { headers: authHeaders() });
            if (!audioRes.ok) throw new Error("오디오 파일 다운로드 실패");
            const audioBlob = await audioRes.blob();

            inlineFill.style.width = "100%";
            inlineStatus.textContent = "저장 중...";
            
            // Build Audiobook entry
            const audioId = crypto.randomUUID();
            const audioArrayBuffer = await audioBlob.arrayBuffer();

            const entry = {
                id: audioId,
                title: audioFilename,
                audioData: audioArrayBuffer, 
                sentences: sentences,
                timestamp: Date.now(),
                dateString: new Date().toLocaleDateString("ko-KR", {
                    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
                }),
                sizeBytes: audioBlob.size,
                charCount: charCount
            };

            await saveAudiobookToDB(entry);

            // 진행 아이템 제거 후 라이브러리 다시 렌더링
            progressItem.remove();
            showToast("저장되었습니다!", "success");
            trackProductEvent("generation_completed");
            renderLibrary();
            // 만들자마자 클라우드에 올린다. 예전에는 페이지 로드 때만
            // 동기화해서, 만든 뒤 바로 로그아웃하면 복구 불가로 사라졌다.
            if (isLoggedIn()) syncWithCloud();
            return true;

        } catch (error) {
            console.error(error);
            progressItem.remove();
            // 리스트가 비었으면 empty 상태 복원
            if (audioList.children.length === 0) {
                libraryEmpty.style.display = "flex";
            }
            showToast(error.message, "error");
            trackProductEvent("generation_failed");
            return false;
        }
    }

    function getAudiobookFromDB(id) {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(["audiobooks"], "readonly");
            const store = transaction.objectStore("audiobooks");
            const request = store.get(id);
            request.onsuccess = (e) => resolve(e.target.result);
            request.onerror = (e) => reject(e.target.error);
        });
    }

    // ----------------------------------------------------
    // 4.5 Default Audiobook Sync
    // 기본 제공 오디오북은 서버가 기동 시 미리 생성해 둔다. 클라이언트는
    // 라이브러리에 해당 책이 없을 때만 서버에서 내려받아 저장한다.
    // ----------------------------------------------------
    const DEFAULT_BOOK_ID = "default-sherlock-holmes";

    async function seedDefaultBookIfNeeded() {
        try {
            const existing = await getAudiobookFromDB(DEFAULT_BOOK_ID);
            let needsUpdate = false;
            let meta = null;

            try {
                const checkRes = await fetch("/api/default-book");
                if (checkRes.ok) {
                    const checkMeta = await checkRes.json();
                    if (checkMeta.status === "ready") {
                        meta = checkMeta;
                        if (!existing || !existing.audioData || existing.version !== meta.version) {
                            needsUpdate = true;
                        }
                    } else if (!existing || !existing.audioData) {
                        needsUpdate = true;
                    }
                } else if (!existing || !existing.audioData) {
                    needsUpdate = true;
                }
            } catch (e) {
                if (!existing || !existing.audioData) needsUpdate = true;
            }

            if (!needsUpdate) return;

            // 라이브러리에 다운로드/생성 중 표시 아이템 미리 추가
            libraryEmpty.style.display = "none";
            const progressItem = document.createElement("div");
            progressItem.className = "audio-item audio-item-generating";
            progressItem.innerHTML = `
                <div class="audio-title-group">
                    <div class="generating-spinner"></div>
                    <div class="generating-info">
                        <span class="audio-title">데미안 (기본 제공)</span>
                        <div class="generating-progress-track">
                            <div class="generating-progress-fill" style="width: 30%"></div>
                        </div>
                        <span class="generating-status">기본 제공 오디오북 준비 중...</span>
                    </div>
                </div>
            `;
            audioList.prepend(progressItem);

            let attempts = 0;
            const maxAttempts = 60; // Max 1 minute polling
            while (attempts < maxAttempts && (!meta || meta.status !== "ready")) {
                try {
                    const metaRes = await fetch("/api/default-book");
                    if (!metaRes.ok) {
                        attempts++;
                        await new Promise(r => setTimeout(r, 2000));
                        continue;
                    }
                    meta = await metaRes.json();

                    if (meta.status === "ready") {
                        break;
                    } else if (meta.status === "error") {
                        console.warn("Default book generation error on server:", meta.error);
                        await new Promise(r => setTimeout(r, 2000));
                    } else {
                        // pending or generating -> wait and retry
                        await new Promise(r => setTimeout(r, 2000));
                    }
                } catch (fetchError) {
                    console.warn("Error fetching default book status:", fetchError);
                    await new Promise(r => setTimeout(r, 2000));
                }
                attempts++;
            }

            if (!meta || meta.status !== "ready") {
                progressItem.remove();
                if (audioList.children.length === 0) {
                    libraryEmpty.style.display = "flex";
                }
                showToast("기본 제공 오디오북을 준비할 수 없습니다. 새 문서를 업로드해 주세요.", "info");
                return;
            }

            progressItem.querySelector(".generating-status").textContent = "다운로드 중...";
            progressItem.querySelector(".generating-progress-fill").style.width = "70%";

            try {
                const audioRes = await fetch(meta.audio_url);
                if (!audioRes.ok) throw new Error("다운로드 실패");
                const audioArrayBuffer = await audioRes.arrayBuffer();

                await saveAudiobookToDB({
                    id: DEFAULT_BOOK_ID,
                    title: meta.title + ".mp3",
                    audioData: audioArrayBuffer,
                    sentences: meta.sentences,
                    headings: meta.headings,
                    timestamp: Date.now(),
                    dateString: new Date().toLocaleDateString("ko-KR", {
                        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    }),
                    sizeBytes: audioArrayBuffer.byteLength,
                    charCount: meta.char_count,
                    isDefault: true,
                    version: meta.version
                });

                progressItem.remove();
                renderLibrary();
                showToast("기본 제공 오디오북이 준비되었습니다!", "success");
            } catch (innerError) {
                console.error("Failed to save default book:", innerError);
                progressItem.remove();
                if (audioList.children.length === 0) {
                    libraryEmpty.style.display = "flex";
                }
                showToast("기본 제공 오디오북 저장에 실패했습니다.", "error");
            }
        } catch (error) {
            // 실패해도 조용히 넘어간다. 다음 방문 때 다시 시도된다.
            console.error("Default book sync failed:", error);
        }
    }

    // ----------------------------------------------------
    // 5. Audiobook Library Management (IndexedDB Powered)
    // ----------------------------------------------------
    async function renderLibrary() {
        // 생성 중인 진행 아이템 백업
        const generatingItems = Array.from(audioList.querySelectorAll(".audio-item-generating"));

        audioList.innerHTML = "";

        try {
            const list = await getAllAudiobooksFromDB();

            if (list.length === 0 && generatingItems.length === 0) {
                libraryEmpty.style.display = "flex";
                return;
            }

            libraryEmpty.style.display = "none";

            // 생성 중인 진행 아이템이 있다면 최상단에 재삽입
            generatingItems.forEach(item => audioList.appendChild(item));

            list.forEach(audio => {
                const item = document.createElement("div");
                item.className = "audio-item";
                const hasSentences = audio.sentences && audio.sentences.length > 0;
                // 클라우드에만 있는 항목은 오디오도 문장도 아직 안 받은 상태다.
                // 받고 나면 둘 다 생기므로 재생 가능한 것으로 보고 클릭을 열어준다.
                const needsDownload = !audio.audioData && !!audio.audioUrl;
                const safeTitle = escapeHtml(getAudiobookDisplayTitle(audio.title));

                item.innerHTML = `
                    <div class="audio-item-bg" data-action="delete" data-id="${audio.id}">
                        <i data-lucide="trash-2"></i>
                    </div>
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="play-circle"></i>
                            <span class="audio-title" title="${safeTitle}">${safeTitle}</span>
                            ${audio.isDefault ? '<span class="default-badge" title="기본 제공 오디오북">기본 제공</span>' : ''}
                        </div>
                        <div class="audio-actions">
                            <button class="btn-icon-round btn-more" data-id="${audio.id}" title="더보기">
                                <i data-lucide="more-horizontal"></i>
                            </button>
                        </div>
                    </div>
                `;

                const front = item.querySelector('.audio-item-front');
                const bg = item.querySelector('.audio-item-bg');
                let startX = 0;
                let startY = 0;
                let currentX = 0;
                let isDragging = false;
                let isSwipe = false;
                
                front.addEventListener('touchstart', (e) => {
                    startX = e.touches[0].clientX;
                    startY = e.touches[0].clientY;
                    currentX = startX;
                    isDragging = true;
                    isSwipe = false;
                    front.classList.add('ui-dragging');
                }, { passive: true });
                
                front.addEventListener('touchmove', (e) => {
                    if (!isDragging) return;
                    const x = e.touches[0].clientX;
                    const y = e.touches[0].clientY;
                    const deltaX = x - startX;
                    const deltaY = y - startY;
                    
                    if (!isSwipe) {
                        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 5) {
                            isSwipe = true;
                        } else if (Math.abs(deltaY) > 5) {
                            isDragging = false;
                            front.classList.remove('ui-dragging');
                            return;
                        }
                    }
                    
                    if (isSwipe) {
                        if (e.cancelable) e.preventDefault();
                        currentX = x;
                        if (deltaX < 0) {
                            // No hard cap, direct tracking
                            bg.style.display = ''; // Show bg
                            front.style.transform = `translateX(${deltaX}px)`;
                        } else if (deltaX > 0) {
                            // Rubber band effect to the right
                            bg.style.display = 'none'; // Hide red bg
                            front.style.transform = `translateX(${deltaX * 0.15}px)`;
                        }
                    }
                }, { passive: false });
                
                front.addEventListener('touchend', (e) => {
                    if (!isDragging) return;
                    isDragging = false;
                    front.classList.remove('ui-dragging');
                    const deltaX = currentX - startX;
                    
                    // Overswipe: -150px 이상 땡기면 삭제 확인 후 애니메이션 발동
                    if (deltaX < -150) {
                        if (navigator.vibrate) navigator.vibrate(50);
                        
                        // 풀 스와이프 시 팝업 띄우기 요청 반영
                        if (confirm("정말 이 오디오북을 삭제하시겠습니까?")) {
                            front.classList.add('deleting');
                            item.classList.add('deleting-row');
                            
                            setTimeout(() => {
                                deleteAudiobook(audio.id);
                            }, 350);
                        } else {
                            // 취소 시 스냅 원상복구
                            front.style.transform = '';
                            item.classList.remove('swipe-open');
                        }
                    } else if (deltaX < -40) {
                        front.style.transform = `translateX(-80px)`;
                        item.classList.add('swipe-open');
                    } else {
                        front.style.transform = '';
                        item.classList.remove('swipe-open');
                    }
                }, { passive: true });

                // Click away to close
                document.addEventListener('touchstart', (e) => {
                    if (item.classList.contains('swipe-open') && !item.contains(e.target)) {
                        front.style.transform = '';
                        item.classList.remove('swipe-open');
                    }
                }, { passive: true });

                // Delete action
                bg.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (!confirm("정말 이 오디오북을 삭제하시겠습니까?")) return;
                    deleteAudiobook(audio.id);
                });

                if (hasSentences || needsDownload) {
                    item.addEventListener("click", async (e) => {
                        if (item.classList.contains('swipe-open')) {
                            front.style.transform = '';
                            item.classList.remove('swipe-open');
                            return;
                        }
                        if (e.target.closest('.btn-more')) return;
                        let freshAudio = await getAudiobookFromDB(audio.id);
                        if (!freshAudio) {
                            showToast("오디오 데이터를 불러올 수 없습니다. 다시 생성해 주세요.", "error");
                            return;
                        }
                        // 클라우드에만 있는 항목이면 이때 내려받아 캐시한다
                        if (!freshAudio.audioData && freshAudio.audioUrl) {
                            showToast("클라우드에서 불러오는 중...", "info");
                            try {
                                freshAudio = await ensureAudioData(freshAudio);
                            } catch (e) {
                                console.error(e);
                                showToast("클라우드에서 오디오를 받지 못했습니다.", "error");
                                return;
                            }
                        }
                        if (!freshAudio.audioData) {
                            showToast("오디오 데이터를 불러올 수 없습니다. 다시 생성해 주세요.", "error");
                            return;
                        }
                        openReaderMode(freshAudio);
                    });
                }

                // '...' 버튼 -> ActionSheet
                item.querySelector(".btn-more").addEventListener("click", (e) => {
                    e.stopPropagation();
                    openActionSheet(audio);
                });

                audioList.appendChild(item);
            });

            lucide.createIcons();
        } catch (error) {
            console.error("Library render error: ", error);
            showToast("도서관 오디오북을 불러올 수 없습니다.", "error");
        }
    }

    // ============================================================
    // 클라우드 동기화 (로컬 우선 + 클라우드 백업)
    //
    // IndexedDB가 재생 원본이다. 클라우드는 백업이자 기기 간 전달 통로이며,
    // 오디오북은 만든 뒤 편집이 없어 생성/삭제만 있으므로 충돌 병합이 없다.
    // 클라우드에만 있는 항목은 목록에 먼저 띄우고 재생할 때 내려받는다 —
    // 로그인하자마자 수십 MB를 몰아서 받지 않기 위해서다.
    // ============================================================

    async function uploadAudiobookToCloud(entry) {
        const res = await fetch("/api/audiobooks", {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                title: entry.title,
                file_name: entry.title,
                duration_seconds: entry.durationSeconds || null
            })
        });
        if (!res.ok) throw new Error("클라우드 등록 실패");
        const { id, audio_upload, sentences_upload } = await res.json();

        // 파일 본체는 서버를 거치지 않고 Supabase로 직접 올린다
        const up = await fetch(audio_upload.signed_url, {
            method: "PUT",
            headers: { "Content-Type": "audio/mpeg" },
            body: entry.audioData
        });
        if (!up.ok) throw new Error("오디오 업로드 실패");

        await fetch(sentences_upload.signed_url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entry.sentences || [])
        });
        return id;
    }

    /** 클라우드에만 있는 항목의 오디오를 받아 IndexedDB에 캐시한다. */
    async function ensureAudioData(entry) {
        if (entry.audioData) return entry;
        if (!entry.audioUrl) return entry;

        const [audioRes, sentRes] = await Promise.all([
            fetch(entry.audioUrl),
            entry.sentencesUrl ? fetch(entry.sentencesUrl) : Promise.resolve(null)
        ]);
        if (!audioRes.ok) throw new Error("오디오 다운로드 실패");

        const buffer = await audioRes.arrayBuffer();
        let sentences = entry.sentences || [];
        if (sentRes && sentRes.ok) {
            try { sentences = await sentRes.json(); } catch (e) { /* 자막 없이도 재생은 된다 */ }
        }

        const filled = { ...entry, audioData: buffer, sentences, sizeBytes: buffer.byteLength, cloudOnly: false };
        await saveAudiobookToDB(filled);
        return filled;
    }

    async function fetchPlaybackState(entry) {
        if (!entry.cloudId || !isLoggedIn()) return entry;
        try {
            const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, {
                headers: authHeaders()
            });
            if (!res.ok) return entry;
            const state = await res.json();
            const updatedAt = Date.parse(state.updated_at || state.last_played_at || "") || 0;
            if (updatedAt <= (entry.playbackUpdatedAt || 0)) return entry;

            const synced = {
                ...entry,
                lastPosition: state.current_time_seconds || 0,
                playbackSpeed: state.playback_speed || 1.0,
                repeatMode: state.repeat_mode || "off",
                playbackUpdatedAt: updatedAt,
            };
            await saveAudiobookToDB(synced);
            return synced;
        } catch (e) {
            console.error("재생 상태 동기화 실패:", e);
            return entry;
        }
    }

    async function savePlaybackState(entry, position) {
        if (!entry.cloudId || !isLoggedIn()) return;
        const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, {
            method: "PUT",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                current_time_seconds: position,
                playback_speed: entry.playbackSpeed || speedOptions[currentSpeedIndex],
                repeat_mode: entry.repeatMode || repeatModes[currentRepeatMode],
            })
        });
        if (!res.ok) throw new Error("재생 상태 저장 실패");
        const state = await res.json();
        entry.playbackUpdatedAt = Date.parse(state.updated_at || state.last_played_at || "") || Date.now();
        await saveAudiobookToDB(entry);
    }

    let syncing = false;
    /**
     * @returns {Promise<{uploaded:number, added:number, failed:number, ok:boolean}>}
     * 로그아웃이 "안 올라간 게 남았는지"를 판단해야 하므로 결과를 돌려준다.
     * 예전에는 실패를 조용히 삼켜서, 업로드가 안 된 채로 기기 데이터가
     * 지워지는 일을 막지 못했다.
     */
    async function syncWithCloud() {
        const result = { uploaded: 0, added: 0, failed: 0, deleted: 0, ok: false };
        if (!isLoggedIn() || syncing) return result;
        syncing = true;
        try {
            const res = await fetch("/api/audiobooks", { headers: authHeaders() });
            if (!res.ok) return result;
            const cloud = (await res.json()).audiobooks || [];
            const local = await getAllAudiobooksFromDB();

            const cloudIds = new Set(cloud.map(c => c.id));

            // 0) 클라우드에 없는 로컬 오디오북 삭제 (동기화 반영)
            // 단, 기본 오디오북은 제외하며, 클라우드에 한 번이라도 올라가서 cloudId를 부여받은 항목만 대상
            for (const item of local) {
                if (item.isDefault) continue;
                if (item.cloudId && !cloudIds.has(item.cloudId)) {
                    await deleteAudiobookFromDB(item.id);
                    result.deleted++;
                }
            }

            // 1) 로컬에만 있는 것 올리기 (기본 제공본과 아직 안 받은 항목은 제외)
            for (const item of local) {
                if (item.isDefault || !item.audioData) continue;
                if (item.cloudId && cloudIds.has(item.cloudId)) continue;
                // 위 0번 단계에서 삭제되었을 수 있으므로 다시 체크
                if (item.cloudId && !cloudIds.has(item.cloudId)) continue;

                try {
                    const cloudId = await uploadAudiobookToCloud(item);
                    await saveAudiobookToDB({ ...item, cloudId });
                    result.uploaded++;
                } catch (e) {
                    console.error("업로드 실패:", item.title, e);
                    result.failed++;
                }
            }

            // 2) 클라우드에만 있는 것 목록에 추가 (오디오는 재생 시 받는다)
            const localByCloudId = new Map(local.filter(i => i.cloudId).map(i => [i.cloudId, i]));
            for (const c of cloud) {
                const existing = localByCloudId.get(c.id);
                if (existing) {
                    const refreshed = await fetchPlaybackState({
                        ...existing,
                        title: c.title || c.file_name || existing.title,
                        audioUrl: c.audio_url,
                        sentencesUrl: c.sentences_url,
                    });
                    await saveAudiobookToDB(refreshed);
                    continue;
                }
                const added = {
                    id: c.id,
                    cloudId: c.id,
                    title: c.title || c.file_name || "제목 없음",
                    audioData: null,
                    sentences: [],
                    audioUrl: c.audio_url,
                    sentencesUrl: c.sentences_url,
                    cloudOnly: true,
                    timestamp: Date.parse(c.created_at) || Date.now(),
                    dateString: new Date(Date.parse(c.created_at) || Date.now()).toLocaleDateString("ko-KR", {
                        year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"
                    }),
                    sizeBytes: 0,
                    charCount: 0
                };
                await saveAudiobookToDB(await fetchPlaybackState(added));
                result.added++;
            }

            result.ok = result.failed === 0;
            if (result.uploaded || result.added) {
                renderLibrary();
                showToast(`동기화 완료 (올림 ${result.uploaded}, 받음 ${result.added})`, "success");
            }
            return result;
        } catch (e) {
            console.error("클라우드 동기화 실패:", e);
            return result;
        } finally {
            syncing = false;
        }
    }

    // 로그아웃(최상위 스코프)이 삭제 전에 업로드를 끝까지 기다려야 하므로
    // 함수를 노출한다. 이벤트 방식은 완료를 기다릴 수 없다.
    window.__syncAudiobooksToCloud = syncWithCloud;

    // --- ActionSheet ---
    const actionSheetBackdrop = document.getElementById("actionSheetBackdrop");
    const actionShareBtn = document.getElementById("actionShareBtn");
    const actionDownloadBtn = document.getElementById("actionDownloadBtn");
    const actionEditTitleBtn = document.getElementById("actionEditTitleBtn");
    const actionDeleteBtn = document.getElementById("actionDeleteBtn");
    const actionCancelBtn = document.getElementById("actionCancelBtn");
    let actionSheetTarget = null; // 현재 선택된 오디오북 객체

    function openActionSheet(audio) {
        actionSheetTarget = audio;
        actionDeleteBtn.style.display = audio.isDefault ? "none" : "";
        actionEditTitleBtn.style.display = audio.isDefault ? "none" : "";
        actionSheetBackdrop.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(actionSheetBackdrop, actionShareBtn);
    }

    function closeActionSheet() {
        actionSheetBackdrop.classList.remove("show");
        actionSheetTarget = null;
        document.body.style.overflow = "";
        restoreModalFocus(actionSheetBackdrop);
    }

    actionCancelBtn.addEventListener("click", closeActionSheet);
    actionSheetBackdrop.addEventListener("click", (e) => {
        if (e.target === actionSheetBackdrop) closeActionSheet();
    });

    // --- Login Prompt ActionSheet ---
    // 오디오북 생성을 시도했는데 비로그인 상태일 때 네이티브 confirm() 대신
    // 앱의 다른 바텀시트와 같은 톤으로 로그인을 유도한다.
    const loginPromptBackdrop = document.getElementById("loginPromptBackdrop");
    const loginPromptConfirmBtn = document.getElementById("loginPromptConfirmBtn");
    const loginPromptCancelBtn = document.getElementById("loginPromptCancelBtn");

    function openLoginPromptSheet() {
        loginPromptBackdrop.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(loginPromptBackdrop, loginPromptConfirmBtn);
    }

    function closeLoginPromptSheet() {
        loginPromptBackdrop.classList.remove("show");
        document.body.style.overflow = "";
        restoreModalFocus(loginPromptBackdrop);
    }

    loginPromptCancelBtn.addEventListener("click", closeLoginPromptSheet);
    loginPromptBackdrop.addEventListener("click", (e) => {
        if (e.target === loginPromptBackdrop) closeLoginPromptSheet();
    });

    loginPromptConfirmBtn.addEventListener("click", () => {
        const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
        const pendingGen = {
            textId: currentTextId,
            textAccessToken: currentTextAccessToken,
            filename: toAudioFilename(originalName),
            charCount: parseInt(charCountBadge.textContent.replace(/[^0-9]/g, "")) || 0,
            voice: voiceSelect.value,
            rate: getFormattedSpeed(parseInt(speedSlider.value)),
            pitch: getFormattedPitch(parseInt(pitchSlider.value))
        };
        sessionStorage.setItem("pendingGeneration", JSON.stringify(pendingGen));

        closeLoginPromptSheet();
        closeGenerationModal();
        const loginBtn = document.getElementById("googleLoginBtn");
        if (loginBtn) {
            loginBtn.scrollIntoView({ behavior: "smooth", block: "center" });
            const googleBtn = loginBtn.querySelector('div[role="button"]');
            if (googleBtn) googleBtn.click();
        }
    });


    function openIndexSheet(headings) {
        const indexSheetList = document.getElementById("indexSheetList");
        const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
        if (!indexSheetList) return;
        indexSheetList.innerHTML = "";

        headings.forEach(item => {
            const div = document.createElement("div");
            div.className = `index-item h${item.level}`;
            
            // h1, h2, h3 시각적 구분 접두사
            const prefix = item.level === 1 ? "• " : (item.level === 2 ? "└ " : "  └ ");
            div.textContent = prefix + (item.text || item.display_text || item.display);

            div.addEventListener("click", () => {
                closeIndexSheet();
                // 해당 문장 위치로 오디오 이동 및 스크롤
                readerAudio.currentTime = (item.startMs || item.start) / 1000;
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                showPauseIcon();

                const targetSpan = document.getElementById(`sent-${item.sentIndex || item.sent_index}`);
                if (targetSpan) {
                    const spanTop = targetSpan.offsetTop;
                    const containerHeight = readerContent.clientHeight;
                    const targetScroll = spanTop - containerHeight / 2 + targetSpan.clientHeight / 2;
                    readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                }
            });

            indexSheetList.appendChild(div);
        });

        indexSheetBackdrop.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(indexSheetBackdrop, document.getElementById("indexSheetCancelBtn"));
    }

    function closeIndexSheet() {
        const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
        if (indexSheetBackdrop) indexSheetBackdrop.classList.remove("show");
        document.body.style.overflow = "";
        if (indexSheetBackdrop) restoreModalFocus(indexSheetBackdrop);
    }

    const indexSheetCancelBtn = document.getElementById("indexSheetCancelBtn");
    const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
    if (indexSheetCancelBtn) indexSheetCancelBtn.addEventListener("click", closeIndexSheet);
    if (indexSheetBackdrop) {
        indexSheetBackdrop.addEventListener("click", (e) => {
            if (e.target === indexSheetBackdrop) closeIndexSheet();
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (loginPromptBackdrop.classList.contains("show")) {
            closeLoginPromptSheet();
        } else if (actionSheetBackdrop.classList.contains("show")) {
            closeActionSheet();
        } else if (indexSheetBackdrop?.classList.contains("show")) {
            closeIndexSheet();
        } else if (generationModal.classList.contains("show")) {
            closeGenerationModal();
        }
    });

    async function performShare(target) {
        try {
            // IndexedDB에서 오디오 데이터 가져오기
            const freshAudio = await getAudiobookFromDB(target.id);
            if (!freshAudio || !freshAudio.audioData) {
                showToast("오디오 데이터를 찾을 수 없습니다.", "error");
                return;
            }

            let share_id = freshAudio.shareId;
            const now = Date.now();
            
            let needsUpload = true;

            if (freshAudio.id === "default_book") {
                share_id = "default_book";
                needsUpload = false;
            } else if (share_id && freshAudio.shareExpiry && freshAudio.shareExpiry > now) {
                try {
                    const checkRes = await fetch(`/api/share/${share_id}`);
                    if (checkRes.ok) {
                        needsUpload = false;
                        showToast("공유 링크 준비 중...", "info");
                    }
                } catch (e) {
                    console.log("Server check failed, will re-upload", e);
                }
            }

            if (needsUpload) {
                showToast("서버에 업로드하여 공유 링크 생성 중...", "info");
                
                const audioBlob = freshAudio.audioData instanceof Blob
                    ? freshAudio.audioData
                    : new Blob([freshAudio.audioData], { type: "audio/mpeg" });

                // 서버에 임시 업로드 (24시간 후 자동 삭제)
                const formData = new FormData();
                formData.append("audio", audioBlob, "audio.mp3");
                formData.append("title", target.title);
                formData.append("sentences", JSON.stringify(freshAudio.sentences || []));

                const response = await fetch("/api/share", { method: "POST", headers: authHeaders(), body: formData });
                if (!response.ok) throw new Error("서버 업로드 실패");

                const result = await response.json();
                share_id = result.share_id;
                
                // DB에 shareId와 만료시간(약 23시간 50분) 업데이트
                freshAudio.shareId = share_id;
                freshAudio.shareExpiry = now + (23 * 60 * 60 * 1000) + (50 * 60 * 1000);
                await saveAudiobookToDB(freshAudio);
            }

            const shareUrl = `${window.location.origin}/share/${share_id}`;

            // 링크 공유
            if (navigator.share) {
                await navigator.share({
                    title: target.title,
                    text: `"${target.title}" - TextAudio 오디오북을 들어보세요`,
                    url: shareUrl
                });
            } else {
                try {
                    await navigator.clipboard.writeText(shareUrl);
                    showToast("공유 링크가 복사되었습니다! (24시간 유효)", "success");
                } catch (clipErr) {
                    prompt("브라우저 보안 설정으로 자동 복사가 제한되었습니다. 아래 링크를 복사하세요:", shareUrl);
                }
            }
        } catch (err) {
            if (err.name !== "AbortError") {
                console.log("Share failed:", err);
                showToast("공유에 실패했습니다.", "error");
            }
        }
    }

    actionShareBtn.addEventListener("click", async () => {
        if (!actionSheetTarget) return;
        const target = actionSheetTarget;
        closeActionSheet();
        await performShare(target);
    });

    actionDownloadBtn.addEventListener("click", async () => {
        if (!actionSheetTarget) return;
        const target = actionSheetTarget;
        closeActionSheet();

        try {
            const freshAudio = await getAudiobookFromDB(target.id);
            if (!freshAudio || !freshAudio.audioData) {
                showToast("오디오 데이터를 찾을 수 없습니다.", "error");
                return;
            }

            const audioBlob = freshAudio.audioData instanceof Blob
                ? freshAudio.audioData
                : new Blob([freshAudio.audioData], { type: "audio/mpeg" });

            const url = URL.createObjectURL(audioBlob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            // 확장자가 없는 경우 .mp3 추가
            let filename = target.title || "audiobook";
            if (!filename.toLowerCase().endsWith(".mp3")) {
                filename += ".mp3";
            }
            a.download = filename;
            
            document.body.appendChild(a);
            a.click();
            
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
            
            showToast("다운로드가 시작되었습니다.", "success");
        } catch (err) {
            console.error("Download error:", err);
            showToast("다운로드에 실패했습니다.", "error");
        }
    });

    actionEditTitleBtn.addEventListener("click", async () => {
        if (!actionSheetTarget || actionSheetTarget.isDefault) return;
        const target = actionSheetTarget;
        closeActionSheet();
        const title = window.prompt("오디오북 제목", getAudiobookDisplayTitle(target.title));
        if (title === null) return;
        const nextTitle = title.trim();
        if (!nextTitle) {
            showToast("제목을 입력해 주세요.", "error");
            return;
        }

        try {
            if (target.cloudId && isLoggedIn()) {
                const res = await fetch(`/api/audiobooks/${target.cloudId}`, {
                    method: "PATCH",
                    headers: { ...authHeaders(), "Content-Type": "application/json" },
                    body: JSON.stringify({ title: nextTitle })
                });
                if (!res.ok) throw new Error("제목 수정 실패");
            }
            await saveAudiobookToDB({ ...target, title: nextTitle });
            renderLibrary();
            showToast("제목을 수정했습니다.", "success");
        } catch (e) {
            console.error(e);
            showToast("제목을 수정하지 못했습니다.", "error");
        }
    });

    if (readerShareBtn) {
        readerShareBtn.addEventListener("click", async () => {
            if (!currentAudioObject) return;
            await performShare(currentAudioObject);
        });
    }

    actionDeleteBtn.addEventListener("click", async () => {
        if (!actionSheetTarget) return;
        if (actionSheetTarget.isDefault) {
            closeActionSheet();
            showToast("기본 제공 오디오북은 삭제할 수 없습니다.", "error");
            return;
        }
        const idToDelete = actionSheetTarget.id;
        closeActionSheet();
        await deleteAudiobook(idToDelete);
    });

    async function deleteAudiobook(id) {
        try {
            // 클라우드에도 있으면 함께 지운다. 안 그러면 다음 동기화 때 되살아난다.
            const entry = await getAudiobookFromDB(id);
            if (entry && entry.cloudId && isLoggedIn()) {
                try {
                    await fetch(`/api/audiobooks/${entry.cloudId}`, {
                        method: "DELETE",
                        headers: authHeaders()
                    });
                } catch (e) {
                    console.error("클라우드 삭제 실패:", e);
                }
            }
            await deleteAudiobookFromDB(id);
            if (objectUrls[id]) {
                URL.revokeObjectURL(objectUrls[id]);
                delete objectUrls[id];
            }
            renderLibrary();
            showToast("제거되었습니다.", "info");
        } catch (e) {
            console.error(e);
            showToast("제거 실패", "error");
        }
    }

    // ----------------------------------------------------
    // 6. Helpers
    // ----------------------------------------------------
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ["Bytes", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    }

    // Web Speech API Fallback System
    let webSpeechSynthesis = window.speechSynthesis;
    let currentUtterance = null;

    function speakWithWebSpeech(text, voice = "ko-KR", rate = 1.0, pitch = 1.0) {
        if (!webSpeechSynthesis) {
            showToast("Web Speech API를 지원하지 않는 브라우저입니다.", "error");
            return;
        }

        webSpeechSynthesis.cancel();
        currentUtterance = new SpeechSynthesisUtterance(text);
        currentUtterance.lang = "ko-KR";
        currentUtterance.rate = rate;
        currentUtterance.pitch = pitch;
        currentUtterance.volume = 1.0;

        currentUtterance.onstart = () => {
            showToast("🎤 Web Speech API로 읽는 중...", "info");
        };
        currentUtterance.onend = () => {
            currentUtterance = null;
        };
        currentUtterance.onerror = (event) => {
            showToast(`Web Speech 오류: ${event.error}`, "error");
        };

        webSpeechSynthesis.speak(currentUtterance);
    }

    function stopWebSpeech() {
        if (webSpeechSynthesis) {
            webSpeechSynthesis.cancel();
            currentUtterance = null;
        }
    }

    // Toast Notification System
    let toastTimeout = null;
    function showToast(message, type = "info") {
        clearTimeout(toastTimeout);
        toastMessage.textContent = message;
        toast.className = "toast";
        toast.classList.add(`toast-${type}`);
        
        // Reader 모드가 열려있으면 상단에서 토스트 표시
        if (readerOverlay.classList.contains("show")) {
            toast.classList.add("toast-top");
        }
        
        let iconName = "info";
        if (type === "success") iconName = "check-circle";
        if (type === "error") iconName = "alert-triangle";
        
        toastIcon.setAttribute("data-lucide", iconName);
        lucide.createIcons();
        
        toast.classList.add("show");
        
        toastTimeout = setTimeout(() => {
            toast.classList.remove("show");
        }, 3500);
    }

    // ----------------------------------------------------
    // 7. Synced Reader Mode Implementation
    // ----------------------------------------------------
    function openReaderMode(audio) {
        if (currentReaderObjectUrl) {
            URL.revokeObjectURL(currentReaderObjectUrl);
            currentReaderObjectUrl = null;
        }

        // ArrayBuffer(신규)든 Blob(구버전 호환)이든 항상 새 Blob으로 재구성
        const audioBlob = audio.audioData instanceof Blob
            ? audio.audioData
            : new Blob([audio.audioData], { type: "audio/mpeg" });

        const localUrl = URL.createObjectURL(audioBlob);
        currentReaderObjectUrl = localUrl;

        currentReadingAudioId = audio.id;
        currentAudioObject = audio;
        trackProductEvent("playback_started");
        lastPositionSaveSecond = -1;
        const savedSpeedIndex = speedOptions.indexOf(audio.playbackSpeed);
        if (savedSpeedIndex !== -1) currentSpeedIndex = savedSpeedIndex;
        const savedRepeatIndex = repeatModes.indexOf(audio.repeatMode);
        if (savedRepeatIndex !== -1) currentRepeatMode = savedRepeatIndex;
        applySpeedUI();
        applyRepeatUI();

        // UI 리셋
        readerBookTitle.textContent = getAudiobookDisplayTitle(audio.title);
        showPlayIcon();
        if (readerShareBtn) readerShareBtn.style.display = "flex";
        readerCurrentTime.textContent = "00:00";
        readerDuration.textContent = "00:00";
        readerProgressFill.style.width = "0%";
        readerContent.innerHTML = "";
        lastActiveSpan = null;
        
        // 문장 및 헤더 렌더링 & Index(목차) 데이터 구성
        const indexHeadings = [];

        function cleanDisplayText(text) {
            let t = (text || "").replace(/[*_~`\\]/g, '');
            t = t.replace(/^#+\s*/, '');
            return t.trim();
        }

        audio.sentences.forEach((s, index) => {
            const rawText = (s.text || "").trim();
            
            let isHeading = false;
            let level = 2;
            let titleText = "";
            
            if (s.type === "heading" && s.display) {
                isHeading = true;
                level = s.level || 2;
                titleText = s.display;
            } else {
                const mdHeadingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
                if (mdHeadingMatch) {
                    isHeading = true;
                    level = mdHeadingMatch[1].length;
                    titleText = cleanDisplayText(mdHeadingMatch[2]);
                }
            }

            if (isHeading && titleText) {
                const headingEl = document.createElement("h" + level);
                headingEl.className = "reader-heading h" + level;

                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = titleText;

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                headingEl.appendChild(span);
                readerContent.appendChild(headingEl);

                indexHeadings.push({
                    text: titleText,
                    level: level,
                    sentIndex: index,
                    startMs: s.start
                });
            } else {
                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = cleanDisplayText(s.text) + " ";

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                readerContent.appendChild(span);
            }
        });

        // 목차(Index) 버튼 표시 제어
        const readerIndexBtn = document.getElementById("readerIndexBtn");
        if (readerIndexBtn) {
            const finalHeadings = (audio.headings && audio.headings.length > 0) ? audio.headings : indexHeadings;
            if (finalHeadings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(finalHeadings);
            } else {
                readerIndexBtn.style.display = "none";
            }
        }
        
        readerOverlay.classList.add("show");
        resetReaderUiTimeout();

        // ==========================================
        // 🚨 iOS Safari 오디오 생명주기 완벽 해결 로직
        // ==========================================
        
        // 1. 메타데이터 로드 완료 시 실행할 초기화 함수 분리
        const initAudioState = () => {
            if (readerAudio.duration && !isNaN(readerAudio.duration)) {
                readerDuration.textContent = formatTime(readerAudio.duration);
            }
            if (audio.lastPosition > 0) {
                readerAudio.currentTime = audio.lastPosition;
            }
            // Apply saved speed
            readerAudio.playbackRate = speedOptions ? speedOptions[currentSpeedIndex] : 1.0;
            readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
            showPauseIcon();
        };

        readerAudio.onerror = () => {
            console.error("Audio load error:", readerAudio.error ? readerAudio.error.code : "unknown");
            showToast(`오디오 로드 실패 (code: ${readerAudio.error ? readerAudio.error.code : '?'})`, "error");
        };

        readerAudio.onloadedmetadata = initAudioState;
        readerAudio.src = localUrl;
        readerAudio.load();
        readerAudio.play().catch(() => {});

        // Play/Pause 토글 함수 (iOS 이중실행 방지)
        let lastToggleTime = 0;
        function togglePlayPause(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            // 300ms 내 이중 호출 방지
            const now = Date.now();
            if (now - lastToggleTime < 300) return;
            lastToggleTime = now;
            
            if (readerAudio.paused) {
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
            } else {
                readerAudio.pause();
            }
        }
        
        // click + touchend 모두 바인드 (이중실행은 위의 debounce로 방지)
        readerPlayPauseBtn.onclick = togglePlayPause;
        readerPlayPauseBtn.addEventListener("touchend", togglePlayPause, { passive: false });
        
        readerAudio.onplay = function() { showPauseIcon(); };
        readerAudio.onpause = function() { showPlayIcon(); };
        
        readerProgressBar.onclick = (e) => {
            const rect = readerProgressBar.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const width = rect.width;
            if (width > 0 && readerAudio.duration) {
                const seekRatio = clickX / width;
                readerAudio.currentTime = seekRatio * readerAudio.duration;
            }
        };
        
        // (이하 하이라이트 및 자동 스크롤 로직 유지)
        readerAudio.ontimeupdate = () => {
            const currentSec = readerAudio.currentTime;
            const currentMs = currentSec * 1000;
            const duration = readerAudio.duration || 0;
            
            readerCurrentTime.textContent = formatTime(currentSec);
            if (duration > 0) {
                readerProgressFill.style.width = `${(currentSec / duration) * 100}%`;
            }
            
            let activeIndex = -1;
            
            for (let i = 0; i < audio.sentences.length; i++) {
                const s = audio.sentences[i];
                if (currentMs >= s.start && currentMs <= s.end) {
                    activeIndex = i;
                    break;
                }
            }
            
            if (activeIndex === -1 && audio.sentences.length > 0) {
                if (currentMs < audio.sentences[0].start) {
                    activeIndex = 0;
                } else {
                    for (let i = audio.sentences.length - 1; i >= 0; i--) {
                        if (currentMs >= audio.sentences[i].start) {
                            activeIndex = i;
                            break;
                        }
                    }
                }
            }
            
            if (activeIndex !== -1) {
                const activeSpan = document.getElementById(`sent-${activeIndex}`);
                if (activeSpan && activeSpan !== lastActiveSpan) {
                    if (lastActiveSpan) {
                        lastActiveSpan.classList.remove("highlight");
                    }
                    activeSpan.classList.add("highlight");
                    
                    isAutoScrolling = true;
                    const spanTop = activeSpan.offsetTop;
                    const containerHeight = readerContent.clientHeight;
                    const targetScroll = spanTop - containerHeight / 2 + activeSpan.clientHeight / 2;
                    readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                    setTimeout(() => { isAutoScrolling = false; }, 800);
                    
                    lastActiveSpan = activeSpan;
                }
            }
            
            // 로컬에는 5초마다 저장하고, 클라우드에는 30초마다만 동기화한다.
            const currentSecond = Math.floor(currentSec);
            if (currentAudioObject && currentSecond % 5 === 0 && currentSecond > 0 && currentSecond !== lastPositionSaveSecond) {
                lastPositionSaveSecond = currentSecond;
                currentAudioObject.playbackSpeed = speedOptions[currentSpeedIndex];
                currentAudioObject.repeatMode = repeatModes[currentRepeatMode];
                updateAudiobookPosition(currentAudioObject.id, currentSec);
                if (Date.now() - lastPlaybackSyncTime >= 30000) {
                    lastPlaybackSyncTime = Date.now();
                    savePlaybackState(currentAudioObject, currentSec).catch((error) => {
                        console.error("재생 상태 저장 실패:", error);
                    });
                }
            }
        };
    }

    function closeReader(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        
        if (currentAudioObject && readerAudio.currentTime > 0) {
            updateAudiobookPosition(currentAudioObject.id, readerAudio.currentTime);
            currentAudioObject.lastPosition = readerAudio.currentTime;
            currentAudioObject.playbackSpeed = speedOptions[currentSpeedIndex];
            currentAudioObject.repeatMode = repeatModes[currentRepeatMode];
            savePlaybackState(currentAudioObject, readerAudio.currentTime).catch((error) => {
                console.error("재생 상태 저장 실패:", error);
            });
        }
        lastPositionSaveSecond = -1;
        
        // closeReader 내부의 이벤트 초기화 부분
        readerAudio.pause();
        
        if (window.clearSleepTimer) window.clearSleepTimer();

        readerAudio.onplay = null;
        readerAudio.onpause = null;
        readerAudio.ontimeupdate = null;
        readerAudio.onloadedmetadata = null;

        readerPlayPauseBtn.onclick = null;
        readerProgressBar.onclick = null;
        
        readerOverlay.classList.remove("show");
        clearTimeout(readerUiTimeout);
        clearTimeout(readerSnapTimeout);
        setReaderUiProgress(0, false);
        lastScrollTop = 0;
        
        showPlayIcon();
        
        if (lastActiveSpan) {
            lastActiveSpan.classList.remove("highlight");
            lastActiveSpan = null;
        }

        const saveSharedBtn = document.getElementById("saveSharedBtn");
        if (saveSharedBtn) {
            saveSharedBtn.style.display = "none";
        }
    }

    closeReaderBtn.addEventListener("click", closeReader);
    closeReaderBtn.addEventListener("touchend", closeReader, { passive: false });

    // Time Formatter (seconds to MM:SS)
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds === Infinity) return "00:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    readerAudio.onerror = () => {
        const err = readerAudio.error;
        console.error("Audio load error:", err ? err.code : "unknown");
        showToast(`오디오 로드 실패 (code: ${err ? err.code : '?'})`, "error");
    };

    // --------------------------------------------------
    // 9. Shared Link Auto-Detection
    // --------------------------------------------------
    function openSharedReaderMode(title, sentences, audioUrl, shareId = null) {
        // 공유 링크로 접속한 수신자를 위한 Reader 모드
        currentReadingAudioId = null;
        currentAudioObject = null;

        readerBookTitle.textContent = getAudiobookDisplayTitle(title);
        showPlayIcon();
        if (readerShareBtn) readerShareBtn.style.display = "none";
        readerCurrentTime.textContent = "00:00";
        readerDuration.textContent = "00:00";
        readerProgressFill.style.width = "0%";
        readerContent.innerHTML = "";
        lastActiveSpan = null;

        // Save Button Logic
        const saveSharedBtn = document.getElementById("saveSharedBtn");
        if (saveSharedBtn) {
            saveSharedBtn.style.display = "flex";
            
            // Clean up previous event listeners by cloning
            const newBtn = saveSharedBtn.cloneNode(true);
            saveSharedBtn.parentNode.replaceChild(newBtn, saveSharedBtn);
            
            newBtn.addEventListener("click", async () => {
                try {
                    showToast("저장 중...", "info");
                    
                    const response = await fetch(audioUrl);
                    if (!response.ok) throw new Error("Audio fetch failed");
                    const audioBlob = await response.blob();
                    
                    const id = Date.now().toString();
                    await saveAudiobookToDB({
                        id,
                        title,
                        audioData: audioBlob,
                        sentences,
                        shareId: shareId, // 다운로드한 파일도 shareId를 기억
                        shareExpiry: Date.now() + (23 * 60 * 60 * 1000) // 만료시간 넉넉히 23시간으로 산정
                    });
                    
                    renderLibrary();
                    newBtn.style.display = "none";
                    showToast("저장되었습니다!", "success");
                } catch (err) {
                    console.error("Save shared audiobook error:", err);
                    showToast("저장 실패했습니다.", "error");
                }
            });
        }

        // 문장 및 헤더 렌더링 & Index(목차) 데이터 구성
        const indexHeadings = [];

        function cleanDisplayText(text) {
            let t = (text || "").replace(/[*_~`\\]/g, '');
            t = t.replace(/^#+\s*/, '');
            return t.trim();
        }

        sentences.forEach((s, index) => {
            const rawText = (s.text || "").trim();
            
            let isHeading = false;
            let level = 2;
            let titleText = "";
            
            if (s.type === "heading" && s.display) {
                isHeading = true;
                level = s.level || 2;
                titleText = s.display;
            } else {
                const mdHeadingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
                if (mdHeadingMatch) {
                    isHeading = true;
                    level = mdHeadingMatch[1].length;
                    titleText = cleanDisplayText(mdHeadingMatch[2]);
                }
            }

            if (isHeading && titleText) {
                const headingEl = document.createElement("h" + level);
                headingEl.className = "reader-heading h" + level;

                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = titleText;

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                headingEl.appendChild(span);
                readerContent.appendChild(headingEl);

                indexHeadings.push({
                    text: titleText,
                    level: level,
                    sentIndex: index,
                    startMs: s.start
                });
            } else {
                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = cleanDisplayText(s.text) + " ";

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                readerContent.appendChild(span);
            }
        });

        // 목차(Index) 버튼 표시 제어
        const readerIndexBtn = document.getElementById("readerIndexBtn");
        if (readerIndexBtn) {
            const finalHeadings = ([] && [].length > 0) ? [] : indexHeadings;
            if (finalHeadings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(finalHeadings);
            } else {
                readerIndexBtn.style.display = "none";
            }
        }

        readerOverlay.classList.add("show");
        resetReaderUiTimeout();

        const initAudioState = () => {
            if (readerAudio.duration && !isNaN(readerAudio.duration)) {
                readerDuration.textContent = formatTime(readerAudio.duration);
            }
            // Apply saved speed
            readerAudio.playbackRate = speedOptions ? speedOptions[currentSpeedIndex] : 1.0;
            readerAudio.play().catch(function(err) { console.log("Autoplay blocked:", err); });
            showPauseIcon();
        };

        readerAudio.onerror = () => {
            console.error("Shared audio load error:", readerAudio.error ? readerAudio.error.code : "unknown");
            showToast("공유 오디오를 불러올 수 없습니다.", "error");
        };

        readerAudio.onloadedmetadata = initAudioState;
        readerAudio.src = audioUrl;
        readerAudio.load();

        let lastToggleTime = 0;
        function togglePlayPause(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            const now = Date.now();
            if (now - lastToggleTime < 300) return;
            lastToggleTime = now;
            if (readerAudio.paused) {
                readerAudio.play().catch(function(err) {
                    console.log("Play failed:", err);
                    const textContent = readerContent.innerText || "";
                    if (textContent.trim() && webSpeechSynthesis) {
                        showToast("오디오 재생 실패. Web Speech API로 읽을까요?", "warning");
                        setTimeout(() => {
                            if (confirm("Web Speech API로 텍스트를 읽으시겠습니까?\n(오디오북을 생성할 수 없는 경우의 대체 방법입니다)")) {
                                const speed = readerAudio.playbackRate || 1.0;
                                speakWithWebSpeech(textContent, "ko-KR", speed, 1.0);
                                showPauseIcon();
                            }
                        }, 100);
                    }
                });
            } else {
                readerAudio.pause();
                stopWebSpeech();
            }
        }

        readerPlayPauseBtn.onclick = togglePlayPause;
        readerPlayPauseBtn.addEventListener("touchend", togglePlayPause, { passive: false });

        readerAudio.onplay = function() { showPauseIcon(); };
        readerAudio.onpause = function() { showPlayIcon(); };

        readerProgressBar.onclick = (e) => {
            const rect = readerProgressBar.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const width = rect.width;
            if (width > 0 && readerAudio.duration) {
                readerAudio.currentTime = (clickX / width) * readerAudio.duration;
            }
        };

        readerAudio.ontimeupdate = () => {
            const currentSec = readerAudio.currentTime;
            const currentMs = currentSec * 1000;
            const duration = readerAudio.duration || 0;

            readerCurrentTime.textContent = formatTime(currentSec);
            if (duration > 0) {
                readerProgressFill.style.width = `${(currentSec / duration) * 100}%`;
            }

            let activeIndex = -1;
            for (let i = 0; i < sentences.length; i++) {
                if (currentMs >= sentences[i].start && currentMs <= sentences[i].end) {
                    activeIndex = i;
                    break;
                }
            }
            if (activeIndex === -1 && sentences.length > 0) {
                if (currentMs < sentences[0].start) {
                    activeIndex = 0;
                } else {
                    for (let i = sentences.length - 1; i >= 0; i--) {
                        if (currentMs >= sentences[i].start) {
                            activeIndex = i;
                            break;
                        }
                    }
                }
            }

            if (activeIndex !== -1) {
                const activeSpan = document.getElementById(`sent-${activeIndex}`);
                if (activeSpan && activeSpan !== lastActiveSpan) {
                    if (lastActiveSpan) lastActiveSpan.classList.remove("highlight");
                    activeSpan.classList.add("highlight");

                    isAutoScrolling = true;
                    const spanTop = activeSpan.offsetTop;
                    const containerHeight = readerContent.clientHeight;
                    const targetScroll = spanTop - containerHeight / 2 + activeSpan.clientHeight / 2;
                    readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                    setTimeout(() => { isAutoScrolling = false; }, 800);

                    lastActiveSpan = activeSpan;
                }
            }
        };
    }

    // 페이지 로드 시 /share/{id} URL 감지
    async function checkSharedLink() {
        const match = window.location.pathname.match(/^\/share\/([a-zA-Z0-9\-]+)$/);
        if (!match) return;

        const shareId = match[1];
        try {
            showToast("공유된 오디오북을 불러오는 중...", "info");
            const response = await fetch(`/api/share/${shareId}`);
            if (!response.ok) {
                if (response.status === 404) {
                    showToast("공유 링크가 만료되었거나 존재하지 않습니다.", "error");
                } else {
                    showToast("오디오북을 불러올 수 없습니다.", "error");
                }
                return;
            }
            const data = await response.json();
            // 약간의 딜레이 후 Reader 열기 (UI 초기화 완료 대기)
            setTimeout(() => {
                openSharedReaderMode(data.title, data.sentences, data.audio_url, shareId);
            }, 500);
        } catch (err) {
            console.error("Failed to load shared audiobook:", err);
            showToast("공유 오디오북 로드에 실패했습니다.", "error");
        }
    }

    // --------------------------------------------------
    // 9.5 Time Skip Controls
    // --------------------------------------------------
    const readerSkipBackBtn = document.getElementById("readerSkipBackBtn");
    const readerSkipForwardBtn = document.getElementById("readerSkipForwardBtn");

    readerSkipBackBtn.addEventListener("click", () => {
        if (readerAudio && !isNaN(readerAudio.currentTime)) {
            readerAudio.currentTime = Math.max(0, readerAudio.currentTime - 10);
        }
    });

    readerSkipForwardBtn.addEventListener("click", () => {
        if (readerAudio && !isNaN(readerAudio.duration)) {
            readerAudio.currentTime = Math.min(readerAudio.duration, readerAudio.currentTime + 10);
        }
    });

    // --------------------------------------------------
    // 10. Secondary Controls (Repeat, Speed & Timer)
    // --------------------------------------------------
    const readerRepeatBtn = document.getElementById("readerRepeatBtn");
    const readerRepeatText = document.getElementById("readerRepeatText");
    const repeatModes = ["off", "all", "one"];
    let currentRepeatMode = 0;

    const savedRepeatMode = localStorage.getItem("textAudio_repeatMode");
    if (savedRepeatMode) {
        const idx = repeatModes.indexOf(savedRepeatMode);
        if (idx !== -1) currentRepeatMode = idx;
    }

    const repeatModeLabels = {
        "off": "반복 안 함",
        "all": "전체 반복",
        "one": "한 곡 반복"
    };

    function applyRepeatUI() {
        const mode = repeatModes[currentRepeatMode];
        readerRepeatText.textContent = repeatModeLabels[mode];
        readerRepeatBtn.classList.toggle("active", mode !== "off");
    }
    applyRepeatUI();

    readerRepeatBtn.addEventListener("click", () => {
        currentRepeatMode = (currentRepeatMode + 1) % repeatModes.length;
        const newMode = repeatModes[currentRepeatMode];
        applyRepeatUI();
        localStorage.setItem("textAudio_repeatMode", newMode);
        showToast(`반복 모드: ${repeatModeLabels[newMode]}`, "info");
    });

    // Handle audio end event for repeat
    readerAudio.addEventListener("ended", () => {
        const mode = repeatModes[currentRepeatMode];
        if (mode === "all") {
            readerAudio.currentTime = 0;
            readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
        } else if (mode === "one") {
            readerAudio.currentTime = 0;
            readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
        }
    });

    const readerSpeedBtn = document.getElementById("readerSpeedBtn");
    const readerSpeedText = document.getElementById("readerSpeedText");
    const speedOptions = [0.75, 1.0, 1.25, 1.5, 2.0];
    let currentSpeedIndex = 1;

    const savedSpeed = localStorage.getItem("textAudio_playbackSpeed");
    if (savedSpeed) {
        const idx = speedOptions.indexOf(parseFloat(savedSpeed));
        if (idx !== -1) currentSpeedIndex = idx;
    }
    
    function applySpeedUI() {
        const speed = speedOptions[currentSpeedIndex];
        readerSpeedText.textContent = speed.toFixed(2).replace(/\.00$/, '.0') + "x";
        readerSpeedBtn.classList.toggle("active", speed !== 1.0);
    }
    applySpeedUI();

    readerSpeedBtn.addEventListener("click", () => {
        currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
        const newSpeed = speedOptions[currentSpeedIndex];
        readerAudio.playbackRate = newSpeed;
        applySpeedUI();
        localStorage.setItem("textAudio_playbackSpeed", newSpeed);
        showToast(`재생 속도 ${newSpeed}x`, "info");
    });

    const readerTimerBtn = document.getElementById("readerTimerBtn");
    const readerTimerText = document.getElementById("readerTimerText");
    const timerOptions = [0, 15, 30, 60];
    let currentTimerIndex = 0;
    let sleepTimerInterval = null;
    let sleepTimeRemaining = 0;

    window.clearSleepTimer = function() {
        clearInterval(sleepTimerInterval);
        readerTimerBtn.classList.remove("active");
        readerTimerText.textContent = "타이머";
        currentTimerIndex = 0;
    };

    function updateTimerDisplay() {
        if (sleepTimeRemaining <= 0) return;
        const m = Math.floor(sleepTimeRemaining / 60);
        const s = sleepTimeRemaining % 60;
        readerTimerText.textContent = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    readerTimerBtn.addEventListener("click", () => {
        currentTimerIndex = (currentTimerIndex + 1) % timerOptions.length;
        const mins = timerOptions[currentTimerIndex];
        
        clearInterval(sleepTimerInterval);

        if (mins === 0) {
            window.clearSleepTimer();
            showToast("취침 타이머가 해제되었습니다.", "info");
        } else {
            readerTimerBtn.classList.add("active");
            sleepTimeRemaining = mins * 60;
            updateTimerDisplay();
            
            sleepTimerInterval = setInterval(() => {
                sleepTimeRemaining--;
                if (sleepTimeRemaining <= 0) {
                    readerAudio.pause();
                    window.clearSleepTimer();
                    showToast("타이머가 종료되어 재생을 멈췄습니다.", "info");
                } else {
                    updateTimerDisplay();
                }
            }, 1000);
            
            showToast(`${mins}분 뒤에 재생이 자동 종료됩니다.`, "info");
        }
    });

    // 미처리된 생성 예약(로그인 팝업 전 저장된 상태)이 있다면 실행
    const pendingGen = sessionStorage.getItem("pendingGeneration");
    if (pendingGen && isLoggedIn()) {
        sessionStorage.removeItem("pendingGeneration");
        try {
            const args = JSON.parse(pendingGen);
            // 비동기로 실행하여 메인 스레드 블로킹 방지
            setTimeout(() => {
                generateAudiobook(args);
            }, 300);
        } catch(e) {
            console.error("Failed to parse pending generation args", e);
        }
    }

    checkSharedLink();

    // iOS PWA Install Prompt
    function initIosPwaPrompt() {
        const promptEl = document.getElementById("iosPwaPrompt");
        const closeBtn = document.getElementById("pwaCloseBtn");
        if (!promptEl || !closeBtn) return;

        // iOS 기기 감지
        const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        // Safari 브라우저 감지 (Chrome 등 기타 웹뷰 제외)
        const isSafari = isIos && /WebKit/.test(navigator.userAgent) && !/CriOS/.test(navigator.userAgent) && !/FxiOS/.test(navigator.userAgent);
        
        // PWA Standalone 모드 여부 감지
        const isStandalone = window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;

        // 이전에 닫기를 누른 기록이 있는지 확인 (7일)
        const lastDismissed = localStorage.getItem("iosPwaPromptDismissed");
        const isDismissedRecently = lastDismissed && (Date.now() - parseInt(lastDismissed, 10)) < (7 * 24 * 60 * 60 * 1000);

        if (isSafari && !isStandalone && !isDismissedRecently) {
            setTimeout(() => {
                promptEl.classList.add("show");
            }, 1500);
        }

        closeBtn.addEventListener("click", () => {
            promptEl.classList.remove("show");
            localStorage.setItem("iosPwaPromptDismissed", Date.now().toString());
        });
    }

    initIosPwaPrompt();
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
        if (hint) hint.style.display = isLoggedIn() ? "none" : "block";
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
        const headerLoginSlot = document.getElementById("headerLoginSlot");

        // 메인 화면은 로그인 여부와 무관하게 항상 보인다 (기본 오디오북 체험용).
        // 전체를 덮는 auth 카드 대신 헤더의 로그인 버튼으로만 유도한다 —
        // 이전에는 authContainer를 무조건 숨겨서 로그인할 방법이 아예 없었다.
        authContainer.style.display = "none";
        appMain.style.display = "flex";

        const loggedIn = !!(user && token);
        userInfo.style.display = loggedIn ? "flex" : "none";
        if (headerLoginSlot) headerLoginSlot.style.display = loggedIn ? "none" : "flex";
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
     * db 핸들이 DOMContentLoaded 스코프 안에 있어 여기서는 따로 연결한다.
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
});
