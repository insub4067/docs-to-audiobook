document.addEventListener("DOMContentLoaded", async () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Check authentication status
    await initializeAuth();

    // DOM Elements
    const voiceSelect = document.getElementById("voiceSelect");
    const voiceDesc = document.getElementById("voiceDesc");
    const voicePreviewBtn = document.getElementById("voicePreviewBtn");
    const voicePreviewLabel = document.getElementById("voicePreviewLabel");
    const libraryEmpty = document.getElementById("libraryEmpty");
    const audioList = document.getElementById("audioList");
    const importLinkBtn = document.getElementById("importLinkBtn");
    
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
        voiceController.stopPreview();
        restoreModalFocus(generationModal);
    }
    
    const loadingOverlay = document.getElementById("loadingOverlay");
    
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
    let objectUrls = {}; 
    let lastActiveSpan = null;
    let currentReadingAudioId = null;
    let currentAudioObject = null;
    let currentReaderObjectUrl = null; 
    let lastPlaybackSyncTime = 0;
    let lastPositionSaveSecond = -1;

    const voiceController = TextAudio.createVoiceController({
        voiceSelect,
        voiceDesc,
        voicePreviewBtn,
        voicePreviewLabel,
        fetch: window.fetch.bind(window),
        createOption: () => document.createElement("option"),
        createAudio: (url) => new Audio(url),
        createObjectURL: (blob) => URL.createObjectURL(blob),
        notify: showToast,
        logError: (error) => console.error(error),
    });
    voiceController.initialize();
    const webSpeechController = TextAudio.createWebSpeechController({
        speechSynthesis: window.speechSynthesis,
        createUtterance: (text) => new SpeechSynthesisUtterance(text),
        notify: showToast,
    });

    // Initialize Database and App
    initDB().then(() => {
        voiceController.loadVoices();
        renderLibrary();
        seedDefaultBookIfNeeded();
        // DB가 열린 뒤에 동기화한다 — 먼저 돌면 db가 null이라 실패한다
        if (isLoggedIn()) syncWithCloud();
    });


    // Background job loading rows
    const generationStatus = TextAudio.createGenerationStatusController({ audioList, libraryEmpty });
    const showBackgroundJobLoading = generationStatus.show;
    const removeBackgroundJobLoading = generationStatus.remove;

    window.__showBackgroundJobLoading = showBackgroundJobLoading;
    window.__removeBackgroundJobLoading = removeBackgroundJobLoading;
    // End background job loading rows


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
        try {
            const list = await getAllAudiobooksFromDB();
            // 생성 중인 진행 아이템 백업
            const generatingItems = Array.from(audioList.querySelectorAll(".audio-item-generating"));
            audioList.innerHTML = "";

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
        const playbackSettings = readerControls.getPlaybackSettings();
        const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, {
            method: "PUT",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                current_time_seconds: position,
                playback_speed: entry.playbackSpeed || playbackSettings.playbackSpeed,
                repeat_mode: entry.repeatMode || playbackSettings.repeatMode,
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
    async function syncWithCloud({ silent = false } = {}) {
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
                if (!silent) {
                    showToast(`동기화 완료 (올림 ${result.uploaded}, 받음 ${result.added})`, "success");
                }
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
    window.__renderLibrary = renderLibrary;

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
    // 체험 한도를 모두 쓴 비로그인 사용자는 네이티브 confirm() 대신
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
        readerControls.applyPlaybackSettings({
            playbackSpeed: audio.playbackSpeed,
            repeatMode: audio.repeatMode,
        });

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

        function createSentenceSpan(s, index, text) {
            const span = document.createElement("span");
            span.className = "reader-sentence";
            span.id = "sent-" + index;
            span.textContent = text;
            span.addEventListener("click", () => {
                readerAudio.currentTime = s.start / 1000;
                readerAudio.play().catch(err => console.log("Play failed:", err));
                showPauseIcon();
            });
            return span;
        }

        for (let index = 0; index < audio.sentences.length; index++) {
            const s = audio.sentences[index];
            if (s.table) {
                const tableId = s.table.id;
                const cells = [];
                while (index < audio.sentences.length && audio.sentences[index].table?.id === tableId) {
                    cells.push({ sentence: audio.sentences[index], index });
                    index++;
                }
                index--;

                const columns = Math.max(...cells.map(cell => cell.sentence.table.column)) + 1;
                const tableEl = document.createElement("table");
                tableEl.className = "reader-table";
                const headerRow = document.createElement("tr");
                const headers = cells.filter(cell => cell.sentence.table.row === 0);
                for (let column = 0; column < columns; column++) {
                    const th = document.createElement("th");
                    th.textContent = headers.find(cell => cell.sentence.table.column === column)?.sentence.table.header || "";
                    headerRow.appendChild(th);
                }
                const thead = document.createElement("thead");
                thead.appendChild(headerRow);
                tableEl.appendChild(thead);
                const tbody = document.createElement("tbody");
                const rows = [...new Set(cells.map(cell => cell.sentence.table.row))];
                rows.forEach(row => {
                    const tr = document.createElement("tr");
                    for (let column = 0; column < columns; column++) {
                        const td = document.createElement("td");
                        const cell = cells.find(item => item.sentence.table.row === row && item.sentence.table.column === column);
                        if (cell) {
                            const text = cleanDisplayText(cell.sentence.text);
                            const prefix = `${cell.sentence.table.header}:`;
                            td.appendChild(createSentenceSpan(
                                cell.sentence,
                                cell.index,
                                text.startsWith(prefix) ? text.slice(prefix.length).trim() : text
                            ));
                        }
                        tr.appendChild(td);
                    }
                    tbody.appendChild(tr);
                });
                tableEl.appendChild(tbody);
                readerContent.appendChild(tableEl);
                continue;
            }
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

                const span = createSentenceSpan(s, index, titleText);

                headingEl.appendChild(span);
                readerContent.appendChild(headingEl);

                indexHeadings.push({
                    text: titleText,
                    level: level,
                    sentIndex: index,
                    startMs: s.start
                });
            } else {
                readerContent.appendChild(createSentenceSpan(s, index, cleanDisplayText(s.text) + " "));
            }
        }

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
            readerAudio.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
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
                    const targetScroll = getReaderScrollTarget(readerContent, activeSpan);
                    readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                    setTimeout(() => { isAutoScrolling = false; }, 800);
                    
                    lastActiveSpan = activeSpan;
                }
            }
            
            // 로컬에는 5초마다 저장하고, 클라우드에는 30초마다만 동기화한다.
            const currentSecond = Math.floor(currentSec);
            if (currentAudioObject && currentSecond % 5 === 0 && currentSecond > 0 && currentSecond !== lastPositionSaveSecond) {
                lastPositionSaveSecond = currentSecond;
                const playbackSettings = readerControls.getPlaybackSettings();
                currentAudioObject.playbackSpeed = playbackSettings.playbackSpeed;
                currentAudioObject.repeatMode = playbackSettings.repeatMode;
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
            const playbackSettings = readerControls.getPlaybackSettings();
            currentAudioObject.playbackSpeed = playbackSettings.playbackSpeed;
            currentAudioObject.repeatMode = playbackSettings.repeatMode;
            savePlaybackState(currentAudioObject, readerAudio.currentTime).catch((error) => {
                console.error("재생 상태 저장 실패:", error);
            });
        }
        lastPositionSaveSecond = -1;
        
        // closeReader 내부의 이벤트 초기화 부분
        readerAudio.pause();
        
        readerControls.clearSleepTimer();

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
            readerAudio.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
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
                                webSpeechController.speak(textContent, "ko-KR", speed, 1.0);
                                showPauseIcon();
                            }
                        }, 100);
                    }
                });
            } else {
                readerAudio.pause();
                webSpeechController.stop();
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
                    const targetScroll = getReaderScrollTarget(readerContent, activeSpan);
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
    const readerRepeatBtn = document.getElementById("readerRepeatBtn");
    const readerRepeatText = document.getElementById("readerRepeatText");
    const readerSpeedBtn = document.getElementById("readerSpeedBtn");
    const readerSpeedText = document.getElementById("readerSpeedText");
    const readerTimerBtn = document.getElementById("readerTimerBtn");
    const readerTimerText = document.getElementById("readerTimerText");
    const readerControls = TextAudio.createReaderControls({
        readerAudio,
        skipBackBtn: readerSkipBackBtn,
        skipForwardBtn: readerSkipForwardBtn,
        repeatBtn: readerRepeatBtn,
        repeatText: readerRepeatText,
        speedBtn: readerSpeedBtn,
        speedText: readerSpeedText,
        timerBtn: readerTimerBtn,
        timerText: readerTimerText,
        storage: localStorage,
        notify: showToast,
        setInterval: window.setInterval.bind(window),
        clearInterval: window.clearInterval.bind(window),
    });
    readerControls.initialize();

    const generationController = TextAudio.createGenerationController({
        voiceController,
        generationStatus,
        openGenerationModal,
        closeGenerationModal,
        openLoginPromptSheet,
        closeLoginPromptSheet,
        renderLibrary,
        syncWithCloud,
    });
    generationController.initialize();

    checkSharedLink();
    initializeBackgroundNotifications();

    initIosPwaPrompt();
});
