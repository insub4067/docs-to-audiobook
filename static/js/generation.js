(function initializeGenerationModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createGenerationController = function createGenerationController({
        voiceController,
        generationStatus,
        openGenerationModal,
        closeGenerationModal,
        openLoginPromptSheet,
        closeLoginPromptSheet,
        renderLibrary,
        syncWithCloud,
    }) {
        const dropzone = document.getElementById("dropzone");
        const fileInput = document.getElementById("fileInput");
        const fileDetails = document.getElementById("fileDetails");
        const fileName = document.getElementById("fileName");
        const fileSize = document.getElementById("fileSize");
        const removeFileBtn = document.getElementById("removeFileBtn");
        const speedSlider = document.getElementById("speedSlider");
        const speedVal = document.getElementById("speedVal");
        const pitchSlider = document.getElementById("pitchSlider");
        const pitchVal = document.getElementById("pitchVal");
        const generateBtn = document.getElementById("generateBtn");
        const previewPlaceholder = document.getElementById("previewPlaceholder");
        const previewText = document.getElementById("previewText");
        const charCountBadge = document.getElementById("charCountBadge");
        const audioList = document.getElementById("audioList");
        const libraryEmpty = document.getElementById("libraryEmpty");
        const urlInput = document.getElementById("urlInput");
        const urlFetchBtn = document.getElementById("urlFetchBtn");
        const urlClearBtn = document.getElementById("urlClearBtn");
        const loginPromptConfirmBtn = document.getElementById("loginPromptConfirmBtn");

        let currentTextId = null;
        let currentTextAccessToken = null;
        let uploadedFile = null;
        let initialized = false;

        const BATCH_CONCURRENCY = 8;

        function getUploadLimitBytes() {
            return document.body.dataset.isAdmin === "true"
                ? 50 * 1024 * 1024
                : 10 * 1024 * 1024;
        }

        function getFormattedSpeed(value) {
            return value >= 0 ? `+${value}%` : `${value}%`;
        }

        function getFormattedPitch(value) {
            return value >= 0 ? `+${value}Hz` : `${value}Hz`;
        }

        function toAudioFilename(originalName) {
            const dot = originalName.lastIndexOf(".");
            const base = dot > 0 ? originalName.substring(0, dot) : originalName;
            return `${base}.mp3`;
        }

        function generationArguments() {
            const originalName = uploadedFile ? uploadedFile.name : "unknown_doc";
            return {
                textId: currentTextId,
                textAccessToken: currentTextAccessToken,
                filename: toAudioFilename(originalName),
                charCount: parseInt(charCountBadge.textContent.replace(/[^0-9]/g, "")) || 0,
                voice: voiceController.getSelectedVoice(),
                rate: getFormattedSpeed(parseInt(speedSlider.value)),
                pitch: getFormattedPitch(parseInt(pitchSlider.value)),
            };
        }

        async function extractText(file) {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("voice", voiceController.getSelectedVoice());
            formData.append("rate", getFormattedSpeed(parseInt(speedSlider.value)));
            formData.append("pitch", getFormattedPitch(parseInt(pitchSlider.value)));

            const response = await fetch("/api/upload", {
                method: "POST",
                headers: authHeaders(),
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "텍스트 추출 실패");
            }
            return response.json();
        }

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
            setTimeout(openGenerationModal, 50);
        }

        function resetSelection() {
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
        }

        async function uploadFile(file) {
            const normal = document.getElementById("dropzoneNormal");
            const loading = document.getElementById("dropzoneLoading");
            if (normal) normal.style.display = "none";
            if (loading) loading.style.display = "block";

            try {
                applyExtractedText(await extractText(file));
            } catch (error) {
                console.error(error);
                showToast(error.message, "error");
                resetSelection();
            } finally {
                if (normal) normal.style.display = "block";
                if (loading) loading.style.display = "none";
            }
        }

        async function handleFileSelect(file) {
            const maxUploadBytes = getUploadLimitBytes();
            if (file.size > maxUploadBytes) {
                showToast(`파일 크기가 너무 큽니다. 최대 ${maxUploadBytes / 1024 / 1024}MB까지 지원합니다.`, "error");
                return;
            }
            uploadedFile = file;
            if (fileName) fileName.textContent = file.name;
            if (fileSize) fileSize.textContent = formatBytes(file.size);
            if (fileDetails) fileDetails.style.display = "block";
            await uploadFile(file);
        }

        async function processBatchFiles(files) {
            const voice = voiceController.getSelectedVoice();
            const rate = getFormattedSpeed(parseInt(speedSlider.value));
            const pitch = getFormattedPitch(parseInt(pitchSlider.value));
            const totalFiles = files.length;
            let completed = 0;
            const queue = files.slice();

            showToast(`${totalFiles}개 파일 배치 변환 시작`, "info");
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
                            pitch,
                        });
                        if (ok) completed += 1;
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

        async function handleBatchFileSelect(files) {
            const validFiles = [];
            for (const file of files) {
                const maxUploadBytes = getUploadLimitBytes();
                if (file.size > maxUploadBytes) {
                    showToast(`${file.name}: 파일이 너무 큽니다 (최대 ${maxUploadBytes / 1024 / 1024}MB)`, "error");
                } else {
                    validFiles.push(file);
                }
            }
            if (validFiles.length === 1) await handleFileSelect(validFiles[0]);
            if (validFiles.length > 1) await processBatchFiles(validFiles);
        }

        async function extractTextFromUrl(url) {
            const response = await fetch("/api/extract-url", {
                method: "POST",
                headers: { ...authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "링크에서 텍스트를 가져오지 못했습니다.");
            return data;
        }

        async function generateAudiobook({ textId, textAccessToken, filename, charCount, voice, rate, pitch }) {
            const isAnonymousTrial = !isLoggedIn();
            if (isAnonymousTrial) {
                if (!(await canStartAnonymousTrial())) {
                    openLoginPromptSheet();
                    return false;
                }
                sessionStorage.setItem("anonymousTrialInProgress", "true");
            }

            libraryEmpty.style.display = "none";
            const progressItem = generationStatus.create(filename);
            audioList.prepend(progressItem);
            setTimeout(() => {
                document.querySelector(".library-section").scrollIntoView({ behavior: "smooth" });
            }, 200);

            const inlineFill = progressItem.querySelector(".generating-progress-fill");
            const inlineStatus = progressItem.querySelector(".generating-status");
            const generationHeaders = isAnonymousTrial ? anonymousSessionHeaders() : authHeaders();

            try {
                trackProductEvent("generation_started");
                const formData = new FormData();
                formData.append("text_id", textId);
                formData.append("text_access_token", textAccessToken);
                formData.append("voice", voice);
                formData.append("rate", rate);
                formData.append("pitch", pitch);

                const response = await fetch("/api/synthesize", {
                    method: "POST",
                    headers: generationHeaders,
                    body: formData,
                });
                if (!response.ok) throw new Error("오디오북 변환 요청 실패. 서버 연결을 확인하세요.");

                const responseData = await response.json();
                const jobId = responseData.job_id;
                if (responseData.background_started) {
                    rememberBackgroundJob(jobId, filename);
                    progressItem.dataset.backgroundJobId = jobId;
                    inlineStatus.textContent = "서버에서 생성 중...";
                    showToast("서버에서 백그라운드 생성이 시작되었습니다. 완료되면 보관함에 저장됩니다.", "info");
                    return true;
                }

                async function pollJobStatus(id) {
                    const pollResponse = await fetch(`/api/job/${id}`, { headers: generationHeaders });
                    if (!pollResponse.ok) throw new Error("작업 상태 통신 실패");
                    const jobData = await pollResponse.json();
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
                        return new Promise((resolve) => {
                            setTimeout(() => resolve(pollJobStatus(id)), 2000);
                        });
                    }
                    if (jobData.status === "completed") return jobData;
                    if (jobData.status === "error") throw new Error(jobData.error || "서버 오디오 변환 에러 발생");
                    throw new Error("알 수 없는 작업 상태입니다.");
                }

                const completedJobData = await pollJobStatus(jobId);
                const audioResponse = await fetch(completedJobData.audio_url, { headers: generationHeaders });
                if (!audioResponse.ok) throw new Error("오디오 파일 다운로드 실패");
                const audioBlob = await audioResponse.blob();
                inlineFill.style.width = "100%";
                inlineStatus.textContent = "저장 중...";

                const entry = {
                    id: crypto.randomUUID(),
                    title: filename,
                    audioData: await audioBlob.arrayBuffer(),
                    sentences: completedJobData.sentences,
                    displayMarkdown: completedJobData.display_markdown || "",
                    timestamp: Date.now(),
                    dateString: new Date().toLocaleDateString("ko-KR", {
                        year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit",
                    }),
                    sizeBytes: audioBlob.size,
                    charCount,
                };
                await saveAudiobookToDB(entry);
                if (isAnonymousTrial) localStorage.setItem("anonymousTrialUsed", "true");
                progressItem.remove();
                showToast("저장되었습니다!", "success");
                trackProductEvent("generation_completed");
                renderLibrary();
                if (isLoggedIn()) syncWithCloud();
                return true;
            } catch (error) {
                console.error(error);
                progressItem.remove();
                if (audioList.children.length === 0) libraryEmpty.style.display = "flex";
                showToast(error.message, "error");
                trackProductEvent("generation_failed");
                return false;
            } finally {
                if (isAnonymousTrial) sessionStorage.removeItem("anonymousTrialInProgress");
            }
        }

        function runPendingGeneration() {
            const pendingGeneration = sessionStorage.getItem("pendingGeneration");
            if (!pendingGeneration || !isLoggedIn()) return;
            sessionStorage.removeItem("pendingGeneration");
            try {
                const arguments_ = JSON.parse(pendingGeneration);
                setTimeout(() => generateAudiobook(arguments_), 300);
            } catch (error) {
                console.error("Failed to parse pending generation args", error);
            }
        }

        function initialize() {
            if (initialized) return;
            initialized = true;

            const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;
            if (isMobileDevice) {
                const dropzoneText = document.querySelector(".dropzone-text");
                const dropzoneHint = document.querySelector(".dropzone-hint");
                if (dropzoneText) dropzoneText.textContent = "이곳을 터치하여 문서를 업로드하세요";
                if (dropzoneHint) dropzoneHint.textContent = "지원: DOCX, PDF, TXT, MD, HWP";
            }

            const openFileInput = () => fileInput.click();
            dropzone.addEventListener("click", openFileInput);
            dropzone.addEventListener("touchend", (event) => {
                event.preventDefault();
                openFileInput();
            });
            fileInput.addEventListener("change", (event) => {
                if (event.target.files.length > 0) handleBatchFileSelect(event.target.files);
            });
            ["dragenter", "dragover"].forEach((eventName) => {
                dropzone.addEventListener(eventName, (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    dropzone.classList.add("dragover");
                }, false);
            });
            ["dragleave", "drop"].forEach((eventName) => {
                dropzone.addEventListener(eventName, (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    dropzone.classList.remove("dragover");
                }, false);
            });
            dropzone.addEventListener("drop", (event) => {
                if (event.dataTransfer.files.length > 0) handleBatchFileSelect(event.dataTransfer.files);
            });
            removeFileBtn?.addEventListener("click", resetSelection);

            urlFetchBtn?.addEventListener("click", async () => {
                const url = (urlInput.value || "").trim();
                if (!url) return;
                if (!isLoggedIn()) {
                    showToast("링크 가져오기는 로그인 후 이용할 수 있습니다.", "info");
                    document.getElementById("headerLoginSlot")?.scrollIntoView({ behavior: "smooth", block: "center" });
                    return;
                }
                urlFetchBtn.disabled = true;
                urlFetchBtn.classList.add("is-loading");
                const label = urlFetchBtn.querySelector("span");
                const originalText = label ? label.textContent : "";
                if (label) label.textContent = "가져오는 중...";
                try {
                    applyExtractedText(await extractTextFromUrl(url));
                    urlInput.value = "";
                    syncUrlClearButton(urlInput, urlClearBtn);
                } catch (error) {
                    console.error(error);
                    showToast(error.message, "error");
                } finally {
                    urlFetchBtn.disabled = false;
                    urlFetchBtn.classList.remove("is-loading");
                    if (label) label.textContent = originalText;
                }
            });
            urlInput?.addEventListener("input", () => syncUrlClearButton(urlInput, urlClearBtn));
            urlInput?.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    urlFetchBtn.click();
                }
            });
            urlClearBtn?.addEventListener("click", () => {
                urlInput.value = "";
                syncUrlClearButton(urlInput, urlClearBtn);
                urlInput.focus();
            });
            document.addEventListener("pointerdown", (event) => {
                if (document.activeElement === urlInput && !event.target.closest(".url-input-row")) urlInput.blur();
            });

            speedSlider.addEventListener("input", (event) => {
                const value = parseInt(event.target.value);
                if (value === 0) speedVal.textContent = "보통 (1.0x)";
                else if (value > 0) speedVal.textContent = `빠름 (1.${value / 5}x)`;
                else speedVal.textContent = `느림 (0.${100 + value * 2}x)`;
            });
            pitchSlider.addEventListener("input", (event) => {
                const value = parseInt(event.target.value);
                if (value === 0) pitchVal.textContent = "기본 (0Hz)";
                else if (value > 0) pitchVal.textContent = `높음 (+${value}Hz)`;
                else pitchVal.textContent = `낮음 (${value}Hz)`;
            });

            generateBtn.addEventListener("click", async () => {
                if (!currentTextId) return;
                closeGenerationModal();
                try {
                    await window.__requestPushNotificationSubscription?.();
                } catch (error) {
                    console.warn("완료 알림 요청 실패");
                }
                await generateAudiobook(generationArguments());
            });

            loginPromptConfirmBtn?.addEventListener("click", () => {
                sessionStorage.setItem("pendingGeneration", JSON.stringify(generationArguments()));
                closeLoginPromptSheet();
                closeGenerationModal();
                const loginButton = document.getElementById("googleLoginBtn");
                loginButton?.scrollIntoView({ behavior: "smooth", block: "center" });
                loginButton?.querySelector('div[role="button"]')?.click();
            });

            runPendingGeneration();
        }

        return { initialize, runPendingGeneration };
    };
})();
