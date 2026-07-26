document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // DOM Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const fileDetails = document.getElementById("fileDetails");
    const fileName = document.getElementById("fileName");
    const fileSize = document.getElementById("fileSize");
    const removeFileBtn = document.getElementById("removeFileBtn");
    
    const voiceSelect = document.getElementById("voiceSelect");
    const voiceDesc = document.getElementById("voiceDesc");
    const speedSlider = document.getElementById("speedSlider");
    const speedVal = document.getElementById("speedVal");
    const pitchSlider = document.getElementById("pitchSlider");
    const pitchVal = document.getElementById("pitchVal");
    
    const generateBtn = document.getElementById("generateBtn");
    const previewPlaceholder = document.getElementById("previewPlaceholder");
    const previewText = document.getElementById("previewText");
    const charCountBadge = document.getElementById("charCountBadge");
    
    const libraryEmpty = document.getElementById("libraryEmpty");
    const audioList = document.getElementById("audioList");
    
    const loadingOverlay = document.getElementById("loadingOverlay");
    const progressBarFill = document.querySelector(".progress-bar-fill");
    const loadingStatus = document.querySelector(".loading-status");
    
    const toast = document.getElementById("toast");
    const toastIcon = document.getElementById("toastIcon");
    const toastMessage = document.getElementById("toastMessage");
    
    // Synced Reader DOM Elements
    const readerOverlay = document.getElementById("readerOverlay");
    const readerBookTitle = document.getElementById("readerBookTitle");
    const closeReaderBtn = document.getElementById("closeReaderBtn");
    const readerContent = document.getElementById("readerContent");
    const readerAudio = document.getElementById("readerAudio");

    // App State
    let currentTextId = null;
    let uploadedFile = null;
    let availableVoices = [];
    let db = null;
    let objectUrls = {}; // Store generated object URLs to clean them up later
    let lastActiveSpan = null;

    // Initialize Database and App
    initDB().then(() => {
        loadVoices();
        renderLibrary();
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
            dropzoneHint.textContent = "지원: DOCX, PDF, TXT";
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
        fileName.textContent = file.name;
        fileSize.textContent = formatBytes(file.size);
        fileDetails.style.display = "block";
        dropzone.style.display = "none";
        
        await uploadFile(file);
    }

    removeFileBtn.addEventListener("click", () => {
        currentTextId = null;
        uploadedFile = null;
        fileInput.value = "";
        
        fileDetails.style.display = "none";
        dropzone.style.display = "flex";
        
        previewText.textContent = "";
        previewText.style.display = "none";
        previewPlaceholder.style.display = "flex";
        
        charCountBadge.style.display = "none";
        charCountBadge.textContent = "0 자";
        
        generateBtn.disabled = true;
    });

    // Upload to Server for High-Speed Parsing
    async function uploadFile(file) {
        previewPlaceholder.style.display = "none";
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
            
            // Mobile UX: Scroll to preview section
            if (window.innerWidth <= 768) {
                setTimeout(() => {
                    document.querySelector(".preview-section").scrollIntoView({ behavior: "smooth" });
                }, 400);
            }
        } catch (error) {
            console.error(error);
            showToast(error.message, "error");
            removeFileBtn.click();
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

        const voice = voiceSelect.value;
        const rate = getFormattedSpeed(parseInt(speedSlider.value));
        const pitch = getFormattedPitch(parseInt(pitchSlider.value));

        loadingOverlay.classList.add("show");
        progressBarFill.style.width = "0%";
        loadingStatus.textContent = "오디오 데이터를 실시간 생성 중...";

        let simulatedProgress = 0;
        const progressInterval = setInterval(() => {
            if (simulatedProgress < 90) {
                simulatedProgress += Math.random() * 6;
                if (simulatedProgress > 90) simulatedProgress = 90;
                progressBarFill.style.width = `${simulatedProgress}%`;
            }
        }, 500);

        try {
            const formData = new FormData();
            formData.append("text_id", currentTextId);
            formData.append("voice", voice);
            formData.append("rate", rate);
            formData.append("pitch", pitch);

            // Fetch the stream as a JSON containing base64 audio and sentence metadata
            const response = await fetch("/api/synthesize", {
                method: "POST",
                body: formData
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                throw new Error("오디오북 실시간 합성 실패. 서버 연결을 확인하세요.");
            }

            const resData = await response.json();
            const audioBase64 = resData.audio;
            const sentences = resData.sentences;

            // Decode base64 to binary Blob
            const byteCharacters = atob(audioBase64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const audioBlob = new Blob([byteArray], { type: "audio/mpeg" });
            
            progressBarFill.style.width = "100%";
            loadingStatus.textContent = "생성 및 로컬 DB 저장 중...";
            
            // Build Audiobook entry
            const audioId = crypto.randomUUID();
            const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
            const audioFilename = originalName.substring(0, originalName.lastIndexOf('.')) + ".mp3";
            
            // Parse char count from badge text (e.g. "1,234 자" -> 1234)
            const rawChars = charCountBadge.textContent.replace(/[^0-9]/g, "");
            const charCount = parseInt(rawChars) || 0;

            const entry = {
                id: audioId,
                title: audioFilename,
                audioData: audioBlob, // Save in local IndexedDB
                sentences: sentences, // Synced reader metadata
                timestamp: Date.now(),
                dateString: new Date().toLocaleDateString("ko-KR", {
                    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
                }),
                sizeBytes: audioBlob.size,
                charCount: charCount
            };
            
            // Save to IndexedDB
            await saveAudiobookToDB(entry);

            setTimeout(() => {
                loadingOverlay.classList.remove("show");
                showToast("오디오북이 브라우저 로컬 DB에 안전하게 소장되었습니다!", "success");
                renderLibrary();
                
                if (window.innerWidth <= 768) {
                    setTimeout(() => {
                        document.querySelector(".library-section").scrollIntoView({ behavior: "smooth" });
                    }, 300);
                }
            }, 800);

        } catch (error) {
            clearInterval(progressInterval);
            console.error(error);
            loadingOverlay.classList.remove("show");
            showToast(error.message, "error");
        }
    });

    // ----------------------------------------------------
    // 5. Audiobook Library Management (IndexedDB Powered)
    // ----------------------------------------------------
    async function renderLibrary() {
        audioList.innerHTML = "";
        
        // Clean up old object URLs from memory to prevent memory leaks
        Object.values(objectUrls).forEach(url => URL.revokeObjectURL(url));
        objectUrls = {};
        
        try {
            const list = await getAllAudiobooksFromDB();
            
            if (list.length === 0) {
                libraryEmpty.style.display = "flex";
                return;
            }
            
            libraryEmpty.style.display = "none";
            
            list.forEach(audio => {
                // Generate a temporary local URL for the Blob
                const localUrl = URL.createObjectURL(audio.audioData);
                objectUrls[audio.id] = localUrl; // cache it to revoke later
                
                const item = document.createElement("div");
                item.className = "audio-item";
                
                const hasSentences = audio.sentences && audio.sentences.length > 0;
                
                item.innerHTML = `
                    <div class="audio-item-header">
                        <div class="audio-title-group">
                            <i data-lucide="headphones"></i>
                            <span class="audio-title" title="${audio.title}">${audio.title}</span>
                        </div>
                        <div class="audio-actions">
                            ${hasSentences ? `
                            <button class="btn-icon-round btn-reader" data-id="${audio.id}" title="독서 모드">
                                <i data-lucide="book-open"></i>
                            </button>
                            ` : ''}
                            <a href="${localUrl}" download="${audio.title}" class="btn-icon-round btn-download" title="다운로드">
                                <i data-lucide="download"></i>
                            </a>
                            <button class="btn-icon-round btn-delete" data-id="${audio.id}" title="삭제">
                                <i data-lucide="trash-2"></i>
                            </button>
                        </div>
                    </div>
                    <div class="audio-meta">
                        <span><i data-lucide="calendar" style="width:12px;height:12px;vertical-align:middle;margin-right:4px;"></i>${audio.dateString}</span>
                        <span><i data-lucide="file-text" style="width:12px;height:12px;vertical-align:middle;margin-right:4px;"></i>${audio.charCount.toLocaleString()} 자</span>
                        <span><i data-lucide="database" style="width:12px;height:12px;vertical-align:middle;margin-right:4px;"></i>${formatBytes(audio.sizeBytes)}</span>
                    </div>
                    <div class="audio-player-wrapper">
                        <audio src="${localUrl}" controls></audio>
                    </div>
                `;
                
                if (hasSentences) {
                    item.querySelector(".btn-reader").addEventListener("click", () => {
                        openReaderMode(audio, localUrl);
                    });
                }
                
                item.querySelector(".btn-delete").addEventListener("click", async (e) => {
                    const idToDelete = e.currentTarget.getAttribute("data-id");
                    await deleteAudiobook(idToDelete);
                });
                
                audioList.appendChild(item);
            });

            lucide.createIcons();
        } catch (error) {
            console.error("Library render error: ", error);
            showToast("도서관 오디오북을 불러올 수 없습니다.", "error");
        }
    }

    async function deleteAudiobook(id) {
        try {
            await deleteAudiobookFromDB(id);
            if (objectUrls[id]) {
                URL.revokeObjectURL(objectUrls[id]);
                delete objectUrls[id];
            }
            renderLibrary();
            showToast("오디오북이 브라우저 로컬 DB에서 제거되었습니다.", "info");
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
    function openReaderMode(audio, localUrl) {
        // Remove file extension for display title
        readerBookTitle.textContent = audio.title.replace(/\.[^/.]+$/, "");
        readerAudio.src = localUrl;
        
        // Reset container
        readerContent.innerHTML = "";
        lastActiveSpan = null;
        
        // Render sentences
        audio.sentences.forEach((s, index) => {
            const span = document.createElement("span");
            span.className = "reader-sentence";
            span.id = `sent-${index}`;
            span.textContent = s.text + " ";
            
            // Allow clicking sentence to skip audio playback directly
            span.addEventListener("click", () => {
                readerAudio.currentTime = s.start / 1000;
                readerAudio.play().catch(err => console.log("Play failed:", err));
            });
            
            readerContent.appendChild(span);
        });
        
        // Show Reader screen
        readerOverlay.classList.add("show");
        
        // Listen to timeupdate to sync highlighting & scrolling
        readerAudio.ontimeupdate = () => {
            const currentMs = readerAudio.currentTime * 1000;
            let activeIndex = -1;
            
            // Find current sentence index
            for (let i = 0; i < audio.sentences.length; i++) {
                const s = audio.sentences[i];
                if (currentMs >= s.start && currentMs <= s.end) {
                    activeIndex = i;
                    break;
                }
            }
            
            // Find closest sentence if boundary gap occurs
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
                    
                    // Smoothly center the reading sentence inside the scrollable container
                    activeSpan.scrollIntoView({ behavior: "smooth", block: "center" });
                    lastActiveSpan = activeSpan;
                }
            }
        };
        
        readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
    }
    
    // Close button
    closeReaderBtn.addEventListener("click", () => {
        readerAudio.pause();
        readerAudio.src = "";
        readerOverlay.classList.remove("show");
        if (lastActiveSpan) {
            lastActiveSpan.classList.remove("highlight");
            lastActiveSpan = null;
        }
    });
});
