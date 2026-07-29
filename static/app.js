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
    
    // Close generation modal
    closeModalBtn.addEventListener("click", () => {
        generationModal.classList.remove("show");
        document.body.style.overflow = "";
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
    let uploadedFile = null;
    let availableVoices = [];
    let db = null;
    let objectUrls = {}; 
    let lastActiveSpan = null;
    let currentReadingAudioId = null;
    let currentAudioObject = null;
    let currentReaderObjectUrl = null; 

    // Initialize Database and App
    initDB().then(() => {
        loadVoices();
        renderLibrary();
        seedDefaultBookIfNeeded();
    });

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
    });

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
                    store.put(data);
                }
                resolve();
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
                
                if (voice.short_name === "ko-KR-SunHiNeural") {
                    option.selected = true;
                }
                
                voiceSelect.appendChild(option);
            });

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

    // 배치는 현재 음성 설정을 모든 파일에 공통 적용하고, 파일마다
    // 추출 → 생성까지 끝낸다. 진행 상황은 라이브러리의 파일별 진행 아이템으로 보여준다.
    async function processBatchFiles(files) {
        const voice = voiceSelect.value;
        const rate = getFormattedSpeed(parseInt(speedSlider.value));
        const pitch = getFormattedPitch(parseInt(pitchSlider.value));

        const totalFiles = files.length;
        let completed = 0;

        showToast(`${totalFiles}개 파일 배치 변환 시작`, "info");

        for (const file of files) {
            try {
                const data = await extractText(file);
                const ok = await generateAudiobook({
                    textId: data.text_id,
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
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "텍스트 추출 실패");
        }

        return await response.json();
    }

    async function uploadFile(file) {
        if (previewPlaceholder) previewPlaceholder.style.display = "none";
        previewText.style.display = "block";
        previewText.innerHTML = '<div style="color: var(--text-muted); text-align: center; margin-top: 40px;"><div class="spinner-container" style="width: 30px; height: 30px; margin: 0 auto 10px;"><div class="double-bounce1"></div><div class="double-bounce2"></div></div>서버에서 고속 문서 해독 중...</div>';

        try {
            const data = await extractText(file);
            currentTextId = data.text_id;

            // Render text preview
            previewText.textContent = data.preview;
            charCountBadge.textContent = `${data.char_count.toLocaleString()} 자`;
            charCountBadge.style.display = "block";
            
            generateBtn.disabled = false;
            
            // Show generation modal instead of confirm alert
            setTimeout(() => {
                generationModal.classList.add("show");
                document.body.style.overflow = "hidden";
            }, 300);
        } catch (error) {
            console.error(error);
            showToast(error.message, "error");
            if (removeFileBtn) removeFileBtn.click();
        }
    }

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

        generationModal.classList.remove("show");
        document.body.style.overflow = "";

        const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
        await generateAudiobook({
            textId: currentTextId,
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
    async function generateAudiobook({ textId, filename, charCount, voice, rate, pitch }) {
        const audioFilename = filename;

        // 라이브러리 섹션에 인라인 진행 아이템 추가
        libraryEmpty.style.display = "none";
        const progressItem = document.createElement("div");
        progressItem.className = "audio-item audio-item-generating";
        progressItem.innerHTML = `
            <div class="audio-title-group">
                <div class="generating-spinner"></div>
                <div class="generating-info">
                    <span class="audio-title">${audioFilename}</span>
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

        let simulatedProgress = 0;
        const progressInterval = setInterval(() => {
            if (simulatedProgress < 90) {
                simulatedProgress += Math.random() * 6;
                if (simulatedProgress > 90) simulatedProgress = 90;
                inlineFill.style.width = `${simulatedProgress}%`;
            }
        }, 500);

        try {
            const formData = new FormData();
            formData.append("text_id", textId);
            formData.append("voice", voice);
            formData.append("rate", rate);
            formData.append("pitch", pitch);

            // 1. Request Job ID from server (Returns immediately)
            const response = await fetch("/api/synthesize", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                clearInterval(progressInterval);
                throw new Error("오디오북 변환 요청 실패. 서버 연결을 확인하세요.");
            }

            const resData = await response.json();
            const jobId = resData.job_id;
            
            // 2. Poll job status until completed
            const pollJobStatus = async (id) => {
                const pollRes = await fetch(`/api/job/${id}`);
                if (!pollRes.ok) throw new Error("작업 상태 통신 실패");
                
                const jobData = await pollRes.json();
                
                if (jobData.status === "processing") {
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
            
            clearInterval(progressInterval);

            const audioBase64 = completedJobData.audio;
            const sentences = completedJobData.sentences;

            // Decode base64 to binary Blob
            const byteCharacters = atob(audioBase64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const audioBlob = new Blob([byteArray], { type: "audio/mpeg" });
            
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
            renderLibrary();
            return true;

        } catch (error) {
            clearInterval(progressInterval);
            console.error(error);
            progressItem.remove();
            // 리스트가 비었으면 empty 상태 복원
            if (audioList.children.length === 0) {
                libraryEmpty.style.display = "flex";
            }
            showToast(error.message, "error");
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
            if (existing && existing.audioData) return;

            // 라이브러리에 다운로드/생성 중 표시 아이템 미리 추가
            libraryEmpty.style.display = "none";
            const progressItem = document.createElement("div");
            progressItem.className = "audio-item audio-item-generating";
            progressItem.innerHTML = `
                <div class="audio-title-group">
                    <div class="generating-spinner"></div>
                    <div class="generating-info">
                        <span class="audio-title">셜록 홈즈의 모험 (기본 제공)</span>
                        <div class="generating-progress-track">
                            <div class="generating-progress-fill" style="width: 30%"></div>
                        </div>
                        <span class="generating-status">기본 제공 오디오북 준비 중...</span>
                    </div>
                </div>
            `;
            audioList.prepend(progressItem);

            let meta = null;
            let attempts = 0;
            const maxAttempts = 60; // Max 1 minute polling
            while (attempts < maxAttempts) {
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
                    isDefault: true
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

                item.innerHTML = `
                    <div class="audio-title-group">
                        <i data-lucide="play-circle"></i>
                        <span class="audio-title" title="${audio.title}">${audio.title}</span>
                        ${audio.isDefault ? '<span class="default-badge" title="기본 제공 오디오북">기본 제공</span>' : ''}
                    </div>
                    <div class="audio-actions">
                        <button class="btn-icon-round btn-more" data-id="${audio.id}" title="더보기">
                            <i data-lucide="more-horizontal"></i>
                        </button>
                    </div>
                `;

                if (hasSentences) {
                    item.addEventListener("click", async (e) => {
                        if (e.target.closest('.btn-more')) return;
                        const freshAudio = await getAudiobookFromDB(audio.id);
                        if (!freshAudio || !freshAudio.audioData) {
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

    // --- ActionSheet ---
    const actionSheetBackdrop = document.getElementById("actionSheetBackdrop");
    const actionShareBtn = document.getElementById("actionShareBtn");
    const actionDownloadBtn = document.getElementById("actionDownloadBtn");
    const actionDeleteBtn = document.getElementById("actionDeleteBtn");
    const actionCancelBtn = document.getElementById("actionCancelBtn");
    let actionSheetTarget = null; // 현재 선택된 오디오북 객체

    function openActionSheet(audio) {
        actionSheetTarget = audio;
        actionDeleteBtn.style.display = audio.isDefault ? "none" : "";
        actionSheetBackdrop.classList.add("show");
        document.body.style.overflow = "hidden";
    }

    function closeActionSheet() {
        actionSheetBackdrop.classList.remove("show");
        actionSheetTarget = null;
        document.body.style.overflow = "";
    }

    actionCancelBtn.addEventListener("click", closeActionSheet);
    actionSheetBackdrop.addEventListener("click", (e) => {
        if (e.target === actionSheetBackdrop) closeActionSheet();
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
    }

    function closeIndexSheet() {
        const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
        if (indexSheetBackdrop) indexSheetBackdrop.classList.remove("show");
        document.body.style.overflow = "";
    }

    const indexSheetCancelBtn = document.getElementById("indexSheetCancelBtn");
    const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
    if (indexSheetCancelBtn) indexSheetCancelBtn.addEventListener("click", closeIndexSheet);
    if (indexSheetBackdrop) {
        indexSheetBackdrop.addEventListener("click", (e) => {
            if (e.target === indexSheetBackdrop) closeIndexSheet();
        });
    }

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

            // 캐시된 shareId가 있고 만료기간(24시간)이 지나지 않았다면 서버에 존재하는지 실제 확인
            if (share_id && freshAudio.shareExpiry && freshAudio.shareExpiry > now) {
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

                const response = await fetch("/api/share", { method: "POST", body: formData });
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

        // UI 리셋
        readerBookTitle.textContent = audio.title.replace(/\.[^/.]+$/, "");
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
            
            // 재생 위치 주기적 저장 (5초마다)
            if (currentAudioObject && Math.floor(currentSec) % 5 === 0 && currentSec > 0) {
                updateAudiobookPosition(currentAudioObject.id, currentSec);
            }
        };
    }

    function closeReader(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        
        if (currentAudioObject && readerAudio.currentTime > 0) {
            updateAudiobookPosition(currentAudioObject.id, readerAudio.currentTime);
            currentAudioObject.lastPosition = readerAudio.currentTime;
        }
        
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

        readerBookTitle.textContent = title;
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

    checkSharedLink();
});

// ============================================================
// Authentication System
// ============================================================

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
            localStorage.removeItem("authToken");
            showAppUI(null, null);
        }
    } else {
        showAppUI(null, null);
    }

    setupAuthEventListeners();
}

function showAuthUI() {
    const authContainer = document.getElementById("authContainer");
    const appMain = document.getElementById("appMain");
    const userInfo = document.getElementById("userInfo");

    authContainer.style.display = "block";
    appMain.style.display = "none";
    userInfo.style.display = "none";
}

function showAppUI(user, token) {
    const authContainer = document.getElementById("authContainer");
    const appMain = document.getElementById("appMain");
    const userInfo = document.getElementById("userInfo");
    const userEmail = document.getElementById("userEmail");

    authContainer.style.display = "none";
    appMain.style.display = "flex";
    if (user && token) {
        userInfo.style.display = "flex";
        userEmail.textContent = user.email;
    } else {
        userInfo.style.display = "none";
    }
}

async function fetchCurrentUser(token) {
    const response = await fetch("/api/auth/me", {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    if (!response.ok) {
        throw new Error("Failed to fetch user");
    }

    return await response.json();
}

async function login(email, password) {
    try {
        const response = await fetch("/api/auth/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (!response.ok) {
            return { success: false, error: data.detail || "로그인 실패" };
        }

        localStorage.setItem("authToken", data.access_token);
        return { success: true, user: data.user };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function register(email, password, fullName) {
    try {
        const response = await fetch("/api/auth/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email,
                password,
                full_name: fullName
            })
        });

        const data = await response.json();

        if (!response.ok) {
            return { success: false, error: data.detail || "가입 실패" };
        }

        return { success: true, message: data.message };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

function logout() {
    localStorage.removeItem("authToken");
    location.reload();
}

function setupAuthEventListeners() {
    const googleLoginBtn = document.getElementById("googleLoginBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    // Google Login Button
    if (googleLoginBtn) {
        googleLoginBtn.addEventListener("click", () => {
            googleLoginBtn.disabled = true;
            googleLoginBtn.textContent = "로그인 중...";
            handleGoogleLogin();
        });
    }



    // Logout button
    if (logoutBtn) {
        logoutBtn.addEventListener("click", logout);
    }
}

// ============================================================
// Google OAuth Handler
// ============================================================

async function handleGoogleLogin() {
    try {
        // Initialize Google OAuth
        google.accounts.id.initialize({
            client_id: "YOUR_GOOGLE_CLIENT_ID",
            callback: onGoogleSignIn
        });

        google.accounts.id.renderButton(
            document.getElementById("googleLoginBtn"),
            { theme: "outline", size: "large" }
        );

        google.accounts.id.prompt();
    } catch (error) {
        console.error("Google login failed:", error);
        showAuthError("Google 로그인에 실패했습니다.");
    }
}

async function onGoogleSignIn(response) {
    const idToken = response.credential;

    try {
        const result = await fetch("/api/auth/google", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ token: idToken })
        });

        const data = await result.json();

        if (!result.ok) {
            throw new Error(data.detail || "로그인 실패");
        }

        // Save token and reload
        localStorage.setItem("authToken", data.access_token);
        setTimeout(() => location.reload(), 500);
    } catch (error) {
        console.error("Auth error:", error);
        showAuthError(error.message || "로그인에 실패했습니다.");
    }
}

function showAuthError(message) {
    const authMessage = document.getElementById("authMessage");
    const googleLoginBtn = document.getElementById("googleLoginBtn");
    
    if (authMessage) {
        authMessage.textContent = message;
        authMessage.classList.add("error");
    }
    
    if (googleLoginBtn) {
        googleLoginBtn.disabled = false;
        googleLoginBtn.textContent = "Google로 계속하기";
    }
}
