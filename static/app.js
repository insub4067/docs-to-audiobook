document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    lucide.createIcons();

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
    const progressBarFill = document.querySelector(".progress-bar-fill");
    const loadingStatus = document.querySelector(".loading-status");
    
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

    function showReaderUi() {
        if (!readerContainer) return;
        readerContainer.classList.remove("hide-ui");
        
        clearTimeout(readerUiTimeout);
        // Auto-hide UI after 4 seconds of inactivity if we are playing
        readerUiTimeout = setTimeout(() => {
            if (!readerAudio.paused) {
                readerContainer.classList.add("hide-ui");
            }
        }, 4000);
    }

    function resetReaderUiTimeout() {
        showReaderUi();
    }
    
    // Close generation modal
    closeModalBtn.addEventListener("click", () => {
        generationModal.classList.remove("show");
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
        if (isAutoScrolling) return; // Ignore automated scrolling (e.g. following text)
        
        const currentScrollTop = readerContent.scrollTop;
        
        if (currentScrollTop > lastScrollTop + 5) {
            // Scrolling down -> Hide UI
            readerContainer.classList.add("hide-ui");
            clearTimeout(readerUiTimeout);
        } else if (currentScrollTop < lastScrollTop - 5) {
            // Scrolling up -> Show UI
            showReaderUi();
        }
        
        lastScrollTop = Math.max(0, currentScrollTop);
    }, { passive: true });
    
    // Touch/Click explicitly shows the UI
    readerContent.addEventListener("click", showReaderUi);
    readerContent.addEventListener("touchstart", showReaderUi, { passive: true });

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

    // 앱이 포그라운드로 돌아올 때마다 체크
    document.addEventListener("visibilitychange", async () => {
        if (document.visibilityState !== "visible") return;
        if (!cachedBuildId) {
            // 아직 초기 ID가 없으면 지금 저장
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
    });

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
                showToast("로컬 데이터베이스를 열 수 없습니다.", "error");
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
                list.sort((a, b) => b.timestamp - a.timestamp);
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
    // ----------------------------------------------------
    if (appVersionDisplay) {
        fetch("/sw.js", { cache: "no-store" })
            .then(res => res.text())
            .then(text => {
                const match = text.match(/CACHE_NAME\s*=\s*["']([^"']+)["']/);
                if (match && match[1]) {
                    appVersionDisplay.textContent = `v ${match[1]}`;
                }
            })
            .catch(err => console.log("Failed to fetch sw version", err));
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
    dropzone.addEventListener("click", () => fileInput.click());
    
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
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
            handleFileSelect(files[0]);
        }
    });

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
    async function uploadFile(file) {
        if (previewPlaceholder) previewPlaceholder.style.display = "none";
        previewText.style.display = "block";
        previewText.innerHTML = '<div style="color: var(--text-muted); text-align: center; margin-top: 40px;"><div class="spinner-container" style="width: 30px; height: 30px; margin: 0 auto 10px;"><div class="double-bounce1"></div><div class="double-bounce2"></div></div>서버에서 고속 문서 해독 중...</div>';
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch("/api/upload", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "텍스트 추출 실패");
            }

            const data = await response.json();
            currentTextId = data.text_id;
            
            // Render text preview
            previewText.textContent = data.preview;
            charCountBadge.textContent = `${data.char_count.toLocaleString()} 자`;
            charCountBadge.style.display = "block";
            
            generateBtn.disabled = false;
            showToast("문서 분석이 완료되었습니다.", "success");
            
            // Show generation modal instead of confirm alert
            setTimeout(() => {
                generationModal.classList.add("show");
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

        const voice = voiceSelect.value;
        const rate = getFormattedSpeed(parseInt(speedSlider.value));
        const pitch = getFormattedPitch(parseInt(pitchSlider.value));

        // 파일 이름 미리 생성
        const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
        const audioFilename = originalName.substring(0, originalName.lastIndexOf('.')) + ".mp3";

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
            formData.append("text_id", currentTextId);
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
            inlineStatus.textContent = "로컬 DB에 저장 중...";
            
            // Build Audiobook entry
            const audioId = crypto.randomUUID();
            
            // Parse char count from badge text (e.g. "1,234 자" -> 1234)
            const rawChars = charCountBadge.textContent.replace(/[^0-9]/g, "");
            const charCount = parseInt(rawChars) || 0;
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
            showToast("오디오북이 브라우저 로컬 DB에 안전하게 소장되었습니다!", "success");
            renderLibrary();

        } catch (error) {
            clearInterval(progressInterval);
            console.error(error);
            progressItem.remove();
            // 리스트가 비었으면 empty 상태 복원
            if (audioList.children.length === 0) {
                libraryEmpty.style.display = "flex";
            }
            showToast(error.message, "error");
        }
    });

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
        actionSheetBackdrop.classList.add("show");
    }

    function closeActionSheet() {
        actionSheetBackdrop.classList.remove("show");
        actionSheetTarget = null;
    }

    actionCancelBtn.addEventListener("click", closeActionSheet);
    actionSheetBackdrop.addEventListener("click", (e) => {
        if (e.target === actionSheetBackdrop) closeActionSheet();
    });

    // ----------------------------------------------------
    // Index ActionSheet (목차 액션시트)
    // ----------------------------------------------------
    const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
    const indexSheetList = document.getElementById("indexSheetList");
    const indexSheetCancelBtn = document.getElementById("indexSheetCancelBtn");

    function openIndexSheet(headings) {
        if (!indexSheetList) return;
        indexSheetList.innerHTML = "";

        headings.forEach(item => {
            const div = document.createElement("div");
            div.className = `index-item h${item.level}`;
            
            // h1, h2, h3 시각적 구분 접두사
            const prefix = item.level === 1 ? "• " : (item.level === 2 ? "└ " : "  └ ");
            div.textContent = prefix + item.text;

            div.addEventListener("click", () => {
                closeIndexSheet();
                // 해당 문장 위치로 오디오 이동 및 스크롤
                readerAudio.currentTime = item.startMs / 1000;
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                showPauseIcon();

                const targetSpan = document.getElementById(`sent-${item.sentIndex}`);
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
    }

    function closeIndexSheet() {
        if (indexSheetBackdrop) indexSheetBackdrop.classList.remove("show");
    }

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
            showToast("오디오북이 제거되었습니다.", "info");
        } catch (e) {
            console.error(e);
            showToast("오디오북 제거 실패", "error");
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
        let hasMarkdownHeadings = false;

        function cleanDisplayText(text) {
            let t = text.replace(/[*_~`\\]/g, '');
            t = t.replace(/^#+\s*/, '');
            return t.trim();
        }

        audio.sentences.forEach((s, index) => {
            const rawText = s.text.trim();
            // 1) 마크다운 # 헤더 또는 2) **굵은글씨**로 이루어진 단독 제목 또는 3) **1\. 숫자목록 제목 감지
            const mdHeadingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
            const boldHeadingMatch = rawText.match(/^(\*\*|__)(.+?)\1$/);
            const numberHeadingMatch = rawText.match(/^(\*\*|__)?(\d+[\.\\\s]+.+?)\1?$/);

            let isHeading = false;
            let level = 2;
            let titleText = "";

            if (mdHeadingMatch) {
                isHeading = true;
                level = mdHeadingMatch[1].length;
                titleText = cleanDisplayText(mdHeadingMatch[2]);
            } else if (boldHeadingMatch && rawText.length < 60) {
                isHeading = true;
                level = 2;
                titleText = cleanDisplayText(boldHeadingMatch[2]);
            } else if (numberHeadingMatch && rawText.length < 40) {
                isHeading = true;
                level = 3;
                titleText = cleanDisplayText(rawText);
            }

            if (isHeading && titleText) {
                hasMarkdownHeadings = true;

                const headingEl = document.createElement(`h${level}`);
                headingEl.className = `reader-heading h${level}`;

                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = `sent-${index}`;
                span.textContent = titleText;

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
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
                span.id = `sent-${index}`;
                span.textContent = cleanDisplayText(s.text) + " ";

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                    showPauseIcon();
                });

                readerContent.appendChild(span);
            }
        });

        // 목차(Index) 버튼 표시 제어
        const readerIndexBtn = document.getElementById("readerIndexBtn");
        if (readerIndexBtn) {
            if (hasMarkdownHeadings && indexHeadings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(indexHeadings);
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

        // Play/Pause 토글 함수 (이중 실행 방지: click 이벤트만 사용)
        let lastToggleTime = 0;
        function togglePlayPause(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            const now = Date.now();
            if (now - lastToggleTime < 300) return;
            lastToggleTime = now;
            
            if (readerAudio.paused) {
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
            } else {
                readerAudio.pause();
            }
        }
        
        readerPlayPauseBtn.onclick = togglePlayPause;
        
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
        if (readerContainer) readerContainer.classList.remove("hide-ui");
        
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
                    showToast("오디오북을 내 서재에 저장하는 중...", "info");
                    
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
                    showToast("내 오디오북에 저장되었습니다!", "success");
                } catch (err) {
                    console.error("Save shared audiobook error:", err);
                    showToast("저장에 실패했습니다.", "error");
                }
            });
        }

        // 문장 및 헤더 렌더링 & Index(목차) 데이터 구성
        const indexHeadings = [];
        let hasMarkdownHeadings = false;

        function cleanDisplayText(text) {
            let t = text.replace(/[*_~`\\]/g, '');
            t = t.replace(/^#+\s*/, '');
            return t.trim();
        }

        sentences.forEach((s, index) => {
            const rawText = s.text.trim();
            const mdHeadingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
            const boldHeadingMatch = rawText.match(/^(\*\*|__)(.+?)\1$/);
            const numberHeadingMatch = rawText.match(/^(\*\*|__)?(\d+[\.\\\s]+.+?)\1?$/);

            let isHeading = false;
            let level = 2;
            let titleText = "";

            if (mdHeadingMatch) {
                isHeading = true;
                level = mdHeadingMatch[1].length;
                titleText = cleanDisplayText(mdHeadingMatch[2]);
            } else if (boldHeadingMatch && rawText.length < 60) {
                isHeading = true;
                level = 2;
                titleText = cleanDisplayText(boldHeadingMatch[2]);
            } else if (numberHeadingMatch && rawText.length < 40) {
                isHeading = true;
                level = 3;
                titleText = cleanDisplayText(rawText);
            }

            if (isHeading && titleText) {
                hasMarkdownHeadings = true;

                const headingEl = document.createElement(`h${level}`);
                headingEl.className = `reader-heading h${level}`;

                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = `sent-${index}`;
                span.textContent = titleText;

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
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
                span.id = `sent-${index}`;
                span.textContent = cleanDisplayText(s.text) + " ";

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                    showPauseIcon();
                });

                readerContent.appendChild(span);
            }
        });

        // 목차(Index) 버튼 표시 제어
        const readerIndexBtn = document.getElementById("readerIndexBtn");
        if (readerIndexBtn) {
            if (hasMarkdownHeadings && indexHeadings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(indexHeadings);
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
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
            } else {
                readerAudio.pause();
            }
        }

        readerPlayPauseBtn.onclick = togglePlayPause;

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
    // 10. Secondary Controls (Speed & Timer)
    // --------------------------------------------------
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
