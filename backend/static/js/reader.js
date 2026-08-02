(function initializeReaderModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createReaderController = function createReaderController(context) {
        const { elements = {}, services, setupSwipeToDismiss, rememberModalFocus, restoreModalFocus } = context;
        const readerOverlay = elements.readerOverlay || document.getElementById("readerOverlay");
        const readerBookTitle = elements.readerBookTitle || document.getElementById("readerBookTitle");
        const readerShareBtn = elements.readerShareBtn || document.getElementById("readerShareBtn");
        const closeReaderBtn = elements.closeReaderBtn || document.getElementById("closeReaderBtn");
        const readerContent = elements.readerContent || document.getElementById("readerContent");
        const readerAudio = elements.readerAudio || document.getElementById("readerAudio");
        const readerPlayPauseBtn = elements.readerPlayPauseBtn || document.getElementById("readerPlayPauseBtn");
        const playIconSvg = elements.playIconSvg || document.getElementById("playIconSvg");
        const pauseIconSvg = elements.pauseIconSvg || document.getElementById("pauseIconSvg");
        const readerCurrentTime = elements.readerCurrentTime || document.getElementById("readerCurrentTime");
        const readerDuration = elements.readerDuration || document.getElementById("readerDuration");
        const readerProgressBar = elements.readerProgressBar || document.getElementById("readerProgressBar");
        const readerProgressFill = elements.readerProgressFill || document.getElementById("readerProgressFill");
        const readerContainer = elements.readerContainer || readerOverlay.querySelector(".reader-container");
        const importLinkBtn = elements.importLinkBtn || document.getElementById("importLinkBtn");
        const indexSheetList = elements.indexSheetList || document.getElementById("indexSheetList");
        const indexSheetBackdrop = elements.indexSheetBackdrop || document.getElementById("indexSheetBackdrop");
        const indexSheetCancelBtn = elements.indexSheetCancelBtn || document.getElementById("indexSheetCancelBtn");
        let saveSharedBtn = elements.saveSharedBtn || document.getElementById("saveSharedBtn");
        const readerIndexBtn = elements.readerIndexBtn || document.getElementById("readerIndexBtn");

        let readerControls;
        let webSpeechController;
        let initialized = false;
        let readerUiTimeout = null;
        let lastScrollTop = 0;
        let isAutoScrolling = false;
        let readerUiProgress = 0;
        let readerSnapTimeout = null;
        let lastActiveSpan = null;
        let currentAudioObject = null;
        let currentReaderObjectUrl = null;
        let lastPlaybackSyncTime = 0;
        let lastPositionSaveSecond = -1;
        const READER_COLLAPSE_DISTANCE = 90;

        function getLibrary() {
            if (!services.library) throw new Error("리더를 초기화하려면 library 서비스가 필요합니다.");
            return services.library;
        }

        function showPlayIcon() {
            if (playIconSvg) playIconSvg.style.display = "";
            if (pauseIconSvg) pauseIconSvg.style.display = "none";
        }

        function showPauseIcon() {
            if (playIconSvg) playIconSvg.style.display = "none";
            if (pauseIconSvg) pauseIconSvg.style.display = "";
        }

        function setReaderUiProgress(progress, animated) {
            if (!readerContainer) return;
            readerUiProgress = Math.min(1, Math.max(0, progress));
            readerContainer.classList.toggle("ui-snapping", animated === true);
            readerContainer.style.setProperty("--reader-ui-p", readerUiProgress.toFixed(3));
        }

        function measureReaderBars() {
            if (!readerContainer) return;
            const header = readerContainer.querySelector(".reader-header");
            const controls = readerContainer.querySelector(".reader-controls");
            const secondary = readerContainer.querySelector(".reader-secondary-controls");
            if (secondary) readerContainer.style.setProperty("--reader-secondary-h", secondary.scrollHeight + "px");
            if (header) readerContainer.style.setProperty("--reader-header-h", header.offsetHeight + "px");
            if (controls) readerContainer.style.setProperty("--reader-controls-h", controls.offsetHeight + "px");
        }

        function showReaderUi() {
            setReaderUiProgress(0, true);
            clearTimeout(readerUiTimeout);
            readerUiTimeout = setTimeout(() => {
                if (!readerAudio.paused) setReaderUiProgress(1, true);
            }, 4000);
        }

        function resetReaderUiTimeout() {
            lastScrollTop = 0;
            setReaderUiProgress(0, false);
            requestAnimationFrame(measureReaderBars);
            showReaderUi();
        }

        function closeIndexSheet() {
            if (indexSheetBackdrop) indexSheetBackdrop.classList.remove("show");
            document.body.style.overflow = "";
            if (indexSheetBackdrop) restoreModalFocus(indexSheetBackdrop);
        }

        function closeIndexSheetIfOpen() {
            if (!indexSheetBackdrop || !indexSheetBackdrop.classList.contains("show")) return false;
            closeIndexSheet();
            return true;
        }

        function openIndexSheet(headings) {
            if (!indexSheetList) return;
            indexSheetList.innerHTML = "";
            headings.forEach(item => {
                const div = document.createElement("div");
                div.className = `index-item h${item.level}`;
                const prefix = item.level === 1 ? "• " : (item.level === 2 ? "└ " : "  └ ");
                div.textContent = prefix + (item.text || item.display_text || item.display);
                div.addEventListener("click", () => {
                    closeIndexSheet();
                    readerAudio.currentTime = (item.startMs || item.start) / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                    const targetSpan = document.getElementById(`sent-${item.sentIndex || item.sent_index}`);
                    if (targetSpan) {
                        const targetScroll = targetSpan.offsetTop - readerContent.clientHeight / 2 + targetSpan.clientHeight / 2;
                        readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                    }
                });
                indexSheetList.appendChild(div);
            });
            indexSheetBackdrop.classList.add("show");
            document.body.style.overflow = "hidden";
            rememberModalFocus(indexSheetBackdrop, indexSheetCancelBtn);
        }

        function renderLocalSentences(audio) {
            const indexHeadings = [];
            function cleanDisplayText(text) {
                let result = (text || "").replace(/[*_~`\\]/g, "");
                result = result.replace(/^#+\s*/, "");
                return result.trim();
            }
            function createSentenceSpan(sentence, index, text) {
                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = text;
                span.addEventListener("click", () => {
                    readerAudio.currentTime = sentence.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });
                return span;
            }
            for (let index = 0; index < audio.sentences.length; index++) {
                const sentence = audio.sentences[index];
                if (sentence.table) {
                    const tableId = sentence.table.id;
                    const cells = [];
                    while (index < audio.sentences.length && audio.sentences[index].table?.id === tableId) {
                        cells.push({ sentence: audio.sentences[index], index });
                        index++;
                    }
                    index--;
                    const columns = Math.max(...cells.map(cell => cell.sentence.table.column)) + 1;
                    const tableElement = document.createElement("table");
                    tableElement.className = "reader-table";
                    const headerRow = document.createElement("tr");
                    const headers = cells.filter(cell => cell.sentence.table.row === 0);
                    for (let column = 0; column < columns; column++) {
                        const header = document.createElement("th");
                        header.textContent = headers.find(cell => cell.sentence.table.column === column)?.sentence.table.header || "";
                        headerRow.appendChild(header);
                    }
                    const head = document.createElement("thead");
                    head.appendChild(headerRow);
                    tableElement.appendChild(head);
                    const body = document.createElement("tbody");
                    const rows = [...new Set(cells.map(cell => cell.sentence.table.row))];
                    rows.forEach(row => {
                        const rowElement = document.createElement("tr");
                        for (let column = 0; column < columns; column++) {
                            const cellElement = document.createElement("td");
                            const cell = cells.find(item => item.sentence.table.row === row && item.sentence.table.column === column);
                            if (cell) {
                                const text = cleanDisplayText(cell.sentence.text);
                                const prefix = `${cell.sentence.table.header}:`;
                                cellElement.appendChild(createSentenceSpan(cell.sentence, cell.index, text.startsWith(prefix) ? text.slice(prefix.length).trim() : text));
                            }
                            rowElement.appendChild(cellElement);
                        }
                        body.appendChild(rowElement);
                    });
                    tableElement.appendChild(body);
                    readerContent.appendChild(tableElement);
                    continue;
                }
                const rawText = (sentence.text || "").trim();
                let isHeading = false;
                let level = 2;
                let titleText = "";
                if (sentence.type === "heading" && sentence.display) {
                    isHeading = true;
                    level = sentence.level || 2;
                    titleText = sentence.display;
                } else {
                    const headingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
                    if (headingMatch) {
                        isHeading = true;
                        level = headingMatch[1].length;
                        titleText = cleanDisplayText(headingMatch[2]);
                    }
                }
                if (isHeading && titleText) {
                    const heading = document.createElement("h" + level);
                    heading.className = "reader-heading h" + level;
                    heading.appendChild(createSentenceSpan(sentence, index, titleText));
                    readerContent.appendChild(heading);
                    indexHeadings.push({ text: titleText, level, sentIndex: index, startMs: sentence.start });
                } else {
                    readerContent.appendChild(createSentenceSpan(sentence, index, cleanDisplayText(sentence.text) + " "));
                }
            }
            const headings = audio.headings && audio.headings.length > 0 ? audio.headings : indexHeadings;
            if (headings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(headings);
            } else {
                readerIndexBtn.style.display = "none";
            }
        }

        function bindLocalPlayback(audio, localUrl) {
            const initAudioState = () => {
                if (readerAudio.duration && !isNaN(readerAudio.duration)) readerDuration.textContent = formatTime(readerAudio.duration);
                if (audio.lastPosition > 0) readerAudio.currentTime = audio.lastPosition;
                readerAudio.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
                readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
                showPauseIcon();
            };
            readerAudio.onerror = () => {
                console.error("Audio load error:", readerAudio.error ? readerAudio.error.code : "unknown");
                showToast(`오디오 로드 실패 (code: ${readerAudio.error ? readerAudio.error.code : "?"})`, "error");
            };
            readerAudio.onloadedmetadata = initAudioState;
            readerAudio.src = localUrl;
            readerAudio.load();
            readerAudio.play().catch(() => {});
            let lastToggleTime = 0;
            function togglePlayPause(event) {
                if (event) { event.preventDefault(); event.stopPropagation(); }
                const now = Date.now();
                if (now - lastToggleTime < 300) return;
                lastToggleTime = now;
                if (readerAudio.paused) readerAudio.play().catch(err => console.log("Play failed:", err));
                else readerAudio.pause();
            }
            readerPlayPauseBtn.onclick = togglePlayPause;
            readerPlayPauseBtn.addEventListener("touchend", togglePlayPause, { passive: false });
            readerAudio.onplay = () => showPauseIcon();
            readerAudio.onpause = () => showPlayIcon();
            readerProgressBar.onclick = event => {
                const rect = readerProgressBar.getBoundingClientRect();
                if (rect.width > 0 && readerAudio.duration) readerAudio.currentTime = ((event.clientX - rect.left) / rect.width) * readerAudio.duration;
            };
            readerAudio.ontimeupdate = () => {
                const currentSec = readerAudio.currentTime;
                const currentMs = currentSec * 1000;
                const duration = readerAudio.duration || 0;
                readerCurrentTime.textContent = formatTime(currentSec);
                if (duration > 0) readerProgressFill.style.width = `${(currentSec / duration) * 100}%`;
                let activeIndex = -1;
                for (let index = 0; index < audio.sentences.length; index++) {
                    if (currentMs >= audio.sentences[index].start && currentMs <= audio.sentences[index].end) { activeIndex = index; break; }
                }
                if (activeIndex === -1 && audio.sentences.length > 0) {
                    if (currentMs < audio.sentences[0].start) activeIndex = 0;
                    else for (let index = audio.sentences.length - 1; index >= 0; index--) if (currentMs >= audio.sentences[index].start) { activeIndex = index; break; }
                }
                if (activeIndex !== -1) {
                    const activeSpan = document.getElementById(`sent-${activeIndex}`);
                    if (activeSpan && activeSpan !== lastActiveSpan) {
                        if (lastActiveSpan) lastActiveSpan.classList.remove("highlight");
                        activeSpan.classList.add("highlight");
                        isAutoScrolling = true;
                        readerContent.scrollTo({ top: getReaderScrollTarget(readerContent, activeSpan), behavior: "smooth" });
                        setTimeout(() => { isAutoScrolling = false; }, 800);
                        lastActiveSpan = activeSpan;
                    }
                }
                const currentSecond = Math.floor(currentSec);
                if (currentAudioObject && currentSecond % 5 === 0 && currentSecond > 0 && currentSecond !== lastPositionSaveSecond) {
                    lastPositionSaveSecond = currentSecond;
                    const playbackSettings = readerControls.getPlaybackSettings();
                    currentAudioObject.playbackSpeed = playbackSettings.playbackSpeed;
                    currentAudioObject.repeatMode = playbackSettings.repeatMode;
                    updateAudiobookPosition(currentAudioObject.id, currentSec);
                    if (Date.now() - lastPlaybackSyncTime >= 30000) {
                        lastPlaybackSyncTime = Date.now();
                        getLibrary().savePlaybackState(currentAudioObject, currentSec).catch(error => console.error("재생 상태 저장 실패:", error));
                    }
                }
            };
        }

        function open(audio) {
            if (currentReaderObjectUrl) {
                URL.revokeObjectURL(currentReaderObjectUrl);
                currentReaderObjectUrl = null;
            }
            const audioBlob = audio.audioData instanceof Blob ? audio.audioData : new Blob([audio.audioData], { type: "audio/mpeg" });
            const localUrl = URL.createObjectURL(audioBlob);
            currentReaderObjectUrl = localUrl;
            currentAudioObject = audio;
            trackProductEvent("playback_started");
            lastPositionSaveSecond = -1;
            readerControls.applyPlaybackSettings({ playbackSpeed: audio.playbackSpeed, repeatMode: audio.repeatMode });
            readerBookTitle.textContent = getAudiobookDisplayTitle(audio.title);
            showPlayIcon();
            if (readerShareBtn) readerShareBtn.style.display = "flex";
            readerCurrentTime.textContent = "00:00";
            readerDuration.textContent = "00:00";
            readerProgressFill.style.width = "0%";
            readerContent.innerHTML = "";
            lastActiveSpan = null;
            renderLocalSentences(audio);
            readerOverlay.classList.add("show");
            resetReaderUiTimeout();
            bindLocalPlayback(audio, localUrl);
        }

        function openSharedReaderMode(title, sentences, audioUrl, shareId = null) {
            currentAudioObject = null;
            readerBookTitle.textContent = getAudiobookDisplayTitle(title);
            showPlayIcon();
            if (readerShareBtn) readerShareBtn.style.display = "none";
            readerCurrentTime.textContent = "00:00";
            readerDuration.textContent = "00:00";
            readerProgressFill.style.width = "0%";
            readerContent.innerHTML = "";
            lastActiveSpan = null;
            if (saveSharedBtn) {
                saveSharedBtn.style.display = "flex";
                const newButton = saveSharedBtn.cloneNode(true);
                saveSharedBtn.parentNode.replaceChild(newButton, saveSharedBtn);
                saveSharedBtn = newButton;
                newButton.addEventListener("click", async () => {
                    try {
                        showToast("저장 중...", "info");
                        const response = await fetch(audioUrl);
                        if (!response.ok) throw new Error("Audio fetch failed");
                        const audioBlob = await response.blob();
                        await saveAudiobookToDB({ id: Date.now().toString(), title, audioData: audioBlob, sentences, shareId, shareExpiry: Date.now() + (23 * 60 * 60 * 1000) });
                        getLibrary().render();
                        newButton.style.display = "none";
                        showToast("저장되었습니다!", "success");
                    } catch (error) {
                        console.error("Save shared audiobook error:", error);
                        showToast("저장 실패했습니다.", "error");
                    }
                });
            }
            const indexHeadings = [];
            function cleanDisplayText(text) {
                let result = (text || "").replace(/[*_~`\\]/g, "");
                result = result.replace(/^#+\s*/, "");
                return result.trim();
            }
            sentences.forEach((sentence, index) => {
                const rawText = (sentence.text || "").trim();
                let isHeading = false;
                let level = 2;
                let titleText = "";
                if (sentence.type === "heading" && sentence.display) { isHeading = true; level = sentence.level || 2; titleText = sentence.display; }
                else {
                    const headingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
                    if (headingMatch) { isHeading = true; level = headingMatch[1].length; titleText = cleanDisplayText(headingMatch[2]); }
                }
                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = isHeading && titleText ? titleText : cleanDisplayText(sentence.text) + " ";
                span.addEventListener("click", () => { readerAudio.currentTime = sentence.start / 1000; readerAudio.play().catch(err => console.log("Play failed:", err)); showPauseIcon(); });
                if (isHeading && titleText) {
                    const heading = document.createElement("h" + level);
                    heading.className = "reader-heading h" + level;
                    heading.appendChild(span);
                    readerContent.appendChild(heading);
                    indexHeadings.push({ text: titleText, level, sentIndex: index, startMs: sentence.start });
                } else readerContent.appendChild(span);
            });
            if (indexHeadings.length > 0) { readerIndexBtn.style.display = "flex"; readerIndexBtn.onclick = () => openIndexSheet(indexHeadings); }
            else readerIndexBtn.style.display = "none";
            readerOverlay.classList.add("show");
            resetReaderUiTimeout();
            readerAudio.onerror = () => { console.error("Shared audio load error:", readerAudio.error ? readerAudio.error.code : "unknown"); showToast("공유 오디오를 불러올 수 없습니다.", "error"); };
            readerAudio.onloadedmetadata = () => {
                if (readerAudio.duration && !isNaN(readerAudio.duration)) readerDuration.textContent = formatTime(readerAudio.duration);
                readerAudio.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
                readerAudio.play().catch(err => console.log("Autoplay blocked:", err));
                showPauseIcon();
            };
            readerAudio.src = audioUrl;
            readerAudio.load();
            let lastToggleTime = 0;
            function togglePlayPause(event) {
                if (event) { event.preventDefault(); event.stopPropagation(); }
                const now = Date.now();
                if (now - lastToggleTime < 300) return;
                lastToggleTime = now;
                if (readerAudio.paused) {
                    readerAudio.play().catch(error => {
                        console.log("Play failed:", error);
                        const textContent = readerContent.innerText || "";
                        if (textContent.trim() && window.speechSynthesis) {
                            showToast("오디오 재생 실패. Web Speech API로 읽을까요?", "warning");
                            setTimeout(() => {
                                if (confirm("Web Speech API로 텍스트를 읽으시겠습니까?\n(오디오북을 생성할 수 없는 경우의 대체 방법입니다)")) {
                                    webSpeechController.speak(textContent, "ko-KR", readerAudio.playbackRate || 1.0, 1.0);
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
            readerAudio.onplay = () => showPauseIcon();
            readerAudio.onpause = () => showPlayIcon();
            readerProgressBar.onclick = event => {
                const rect = readerProgressBar.getBoundingClientRect();
                if (rect.width > 0 && readerAudio.duration) readerAudio.currentTime = ((event.clientX - rect.left) / rect.width) * readerAudio.duration;
            };
            readerAudio.ontimeupdate = () => {
                const currentSec = readerAudio.currentTime;
                const currentMs = currentSec * 1000;
                const duration = readerAudio.duration || 0;
                readerCurrentTime.textContent = formatTime(currentSec);
                if (duration > 0) readerProgressFill.style.width = `${(currentSec / duration) * 100}%`;
                let activeIndex = -1;
                for (let index = 0; index < sentences.length; index++) {
                    if (currentMs >= sentences[index].start && currentMs <= sentences[index].end) { activeIndex = index; break; }
                }
                if (activeIndex === -1 && sentences.length > 0) {
                    if (currentMs < sentences[0].start) activeIndex = 0;
                    else for (let index = sentences.length - 1; index >= 0; index--) if (currentMs >= sentences[index].start) { activeIndex = index; break; }
                }
                if (activeIndex !== -1) {
                    const activeSpan = document.getElementById(`sent-${activeIndex}`);
                    if (activeSpan && activeSpan !== lastActiveSpan) {
                        if (lastActiveSpan) lastActiveSpan.classList.remove("highlight");
                        activeSpan.classList.add("highlight");
                        isAutoScrolling = true;
                        readerContent.scrollTo({ top: getReaderScrollTarget(readerContent, activeSpan), behavior: "smooth" });
                        setTimeout(() => { isAutoScrolling = false; }, 800);
                        lastActiveSpan = activeSpan;
                    }
                }
            };
        }

        function closeReader(event) {
            if (event) { event.preventDefault(); event.stopPropagation(); }
            if (currentAudioObject && readerAudio.currentTime > 0) {
                updateAudiobookPosition(currentAudioObject.id, readerAudio.currentTime);
                currentAudioObject.lastPosition = readerAudio.currentTime;
                const playbackSettings = readerControls.getPlaybackSettings();
                currentAudioObject.playbackSpeed = playbackSettings.playbackSpeed;
                currentAudioObject.repeatMode = playbackSettings.repeatMode;
                getLibrary().savePlaybackState(currentAudioObject, readerAudio.currentTime).catch(error => console.error("재생 상태 저장 실패:", error));
            }
            lastPositionSaveSecond = -1;
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
            if (lastActiveSpan) { lastActiveSpan.classList.remove("highlight"); lastActiveSpan = null; }
            if (saveSharedBtn) saveSharedBtn.style.display = "none";
        }

        async function checkSharedLink() {
            const match = window.location.pathname.match(/^\/share\/([a-zA-Z0-9\-]+)$/);
            if (!match) return;
            const shareId = match[1];
            try {
                showToast("공유된 오디오북을 불러오는 중...", "info");
                const response = await fetch(`/api/share/${shareId}`);
                if (!response.ok) { showToast(response.status === 404 ? "공유 링크가 만료되었거나 존재하지 않습니다." : "오디오북을 불러올 수 없습니다.", "error"); return; }
                const data = await response.json();
                setTimeout(() => openSharedReaderMode(data.title, data.sentences, data.audio_url, shareId), 500);
            } catch (error) {
                console.error("Failed to load shared audiobook:", error);
                showToast("공유 오디오북 로드에 실패했습니다.", "error");
            }
        }

        function initialize() {
            if (initialized) return;
            if (!services.library) throw new Error("리더를 초기화하려면 library 서비스가 필요합니다.");
            initialized = true;
            readerControls = window.TextAudio.createReaderControls({
                readerAudio,
                skipBackBtn: elements.readerSkipBackBtn || document.getElementById("readerSkipBackBtn"),
                skipForwardBtn: elements.readerSkipForwardBtn || document.getElementById("readerSkipForwardBtn"),
                repeatBtn: elements.readerRepeatBtn || document.getElementById("readerRepeatBtn"),
                repeatText: elements.readerRepeatText || document.getElementById("readerRepeatText"),
                speedBtn: elements.readerSpeedBtn || document.getElementById("readerSpeedBtn"),
                speedText: elements.readerSpeedText || document.getElementById("readerSpeedText"),
                timerBtn: elements.readerTimerBtn || document.getElementById("readerTimerBtn"),
                timerText: elements.readerTimerText || document.getElementById("readerTimerText"),
                storage: window.localStorage, notify: showToast, setInterval: window.setInterval.bind(window), clearInterval: window.clearInterval.bind(window),
            });
            readerControls.initialize();
            webSpeechController = window.TextAudio.createWebSpeechController({ speechSynthesis: window.speechSynthesis, createUtterance: text => new SpeechSynthesisUtterance(text), notify: showToast });
            if (setupSwipeToDismiss) setupSwipeToDismiss(indexSheetBackdrop, ".index-sheet");
            indexSheetCancelBtn.addEventListener("click", closeIndexSheet);
            indexSheetBackdrop.addEventListener("click", event => { if (event.target === indexSheetBackdrop) closeIndexSheet(); });
            closeReaderBtn.addEventListener("click", closeReader);
            closeReaderBtn.addEventListener("touchend", closeReader, { passive: false });
            importLinkBtn.addEventListener("click", async () => {
                const url = prompt("공유받은 링크를 붙여넣어 주세요:\n(예: https://.../share/...)");
                if (!url) return;
                try {
                    const match = url.match(/\/share\/([a-zA-Z0-9-]+)/);
                    if (!match) { showToast("유효한 공유 링크가 아닙니다.", "error"); return; }
                    showToast("공유 링크 정보를 불러오는 중...", "info");
                    const response = await fetch(`/api/share/${match[1]}`);
                    if (!response.ok) throw new Error("공유 링크가 만료되었거나 존재하지 않습니다.");
                    const data = await response.json();
                    openSharedReaderMode(data.title, data.sentences, data.audio_url, match[1]);
                } catch (error) { console.error(error); showToast(error.message || "공유 링크 불러오기에 실패했습니다.", "error"); }
            });
            readerContent.addEventListener("scroll", () => {
                const scrollTop = readerContent.scrollTop;
                if (isAutoScrolling) { lastScrollTop = Math.max(0, scrollTop); return; }
                const delta = scrollTop - lastScrollTop;
                lastScrollTop = Math.max(0, scrollTop);
                if (scrollTop <= 0) setReaderUiProgress(0, true);
                else { setReaderUiProgress(readerUiProgress + delta / READER_COLLAPSE_DISTANCE, false); clearTimeout(readerUiTimeout); }
                clearTimeout(readerSnapTimeout);
                readerSnapTimeout = setTimeout(() => setReaderUiProgress(readerUiProgress > 0.5 ? 1 : 0, true), 140);
            }, { passive: true });
            readerContent.addEventListener("click", showReaderUi);
            readerContent.addEventListener("touchstart", showReaderUi, { passive: true });
            window.addEventListener("resize", () => { if (readerOverlay.classList.contains("show")) measureReaderBars(); });
        }

        return { initialize, open, getCurrentAudio: () => currentAudioObject, getPlaybackSettings: () => readerControls.getPlaybackSettings(), closeIndexSheetIfOpen, checkSharedLink };
    };
})();
