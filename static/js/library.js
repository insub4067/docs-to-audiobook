(function initializeLibraryModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createLibraryController = function createLibraryController({
        audioList,
        libraryEmpty,
        readerControls,
        openReaderMode,
        getCurrentAudio,
        rememberModalFocus,
        restoreModalFocus,
        objectUrls,
    }) {
        const DEFAULT_BOOK_ID = "default-sherlock-holmes";
        const actionSheetBackdrop = document.getElementById("actionSheetBackdrop");
        const actionShareBtn = document.getElementById("actionShareBtn");
        const actionDownloadBtn = document.getElementById("actionDownloadBtn");
        const actionEditTitleBtn = document.getElementById("actionEditTitleBtn");
        const actionDeleteBtn = document.getElementById("actionDeleteBtn");
        const actionCancelBtn = document.getElementById("actionCancelBtn");
        const readerShareBtn = document.getElementById("readerShareBtn");
        let actionSheetTarget = null;
        let syncing = false;
        let initialized = false;

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
                            if (!existing || !existing.audioData || existing.version !== meta.version) needsUpdate = true;
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

                libraryEmpty.style.display = "none";
                const progressItem = document.createElement("div");
                progressItem.className = "audio-item audio-item-generating";
                progressItem.innerHTML = `
                    <div class="audio-title-group">
                        <div class="generating-spinner"></div>
                        <div class="generating-info">
                            <span class="audio-title">데미안 (기본 제공)</span>
                            <div class="generating-progress-track"><div class="generating-progress-fill" style="width: 30%"></div></div>
                            <span class="generating-status">기본 제공 오디오북 준비 중...</span>
                        </div>
                    </div>`;
                audioList.prepend(progressItem);

                let attempts = 0;
                while (attempts < 60 && (!meta || meta.status !== "ready")) {
                    try {
                        const metaRes = await fetch("/api/default-book");
                        if (!metaRes.ok) {
                            attempts++;
                            await new Promise(resolve => setTimeout(resolve, 2000));
                            continue;
                        }
                        meta = await metaRes.json();
                        if (meta.status === "ready") break;
                        if (meta.status === "error") console.warn("Default book generation error on server:", meta.error);
                    } catch (fetchError) {
                        console.warn("Error fetching default book status:", fetchError);
                    }
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    attempts++;
                }
                if (!meta || meta.status !== "ready") {
                    progressItem.remove();
                    if (audioList.children.length === 0) libraryEmpty.style.display = "flex";
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
                        id: DEFAULT_BOOK_ID, title: meta.title + ".mp3", audioData: audioArrayBuffer,
                        sentences: meta.sentences, headings: meta.headings, timestamp: Date.now(),
                        dateString: new Date().toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }),
                        sizeBytes: audioArrayBuffer.byteLength, charCount: meta.char_count, isDefault: true, version: meta.version,
                    });
                    progressItem.remove();
                    render();
                    showToast("기본 제공 오디오북이 준비되었습니다!", "success");
                } catch (innerError) {
                    console.error("Failed to save default book:", innerError);
                    progressItem.remove();
                    if (audioList.children.length === 0) libraryEmpty.style.display = "flex";
                    showToast("기본 제공 오디오북 저장에 실패했습니다.", "error");
                }
            } catch (error) {
                console.error("Default book sync failed:", error);
            }
        }

        async function render() {
            try {
                const list = await getAllAudiobooksFromDB();
                const generatingItems = Array.from(audioList.querySelectorAll(".audio-item-generating"));
                audioList.innerHTML = "";
                if (list.length === 0 && generatingItems.length === 0) {
                    libraryEmpty.style.display = "flex";
                    return;
                }
                libraryEmpty.style.display = "none";
                generatingItems.forEach(item => audioList.appendChild(item));
                list.forEach(audio => renderAudioItem(audio));
                lucide.createIcons();
            } catch (error) {
                console.error("Library render error: ", error);
                showToast("도서관 오디오북을 불러올 수 없습니다.", "error");
            }
        }

        function renderAudioItem(audio) {
            const item = document.createElement("div");
            item.className = "audio-item";
            const hasSentences = audio.sentences && audio.sentences.length > 0;
            const needsDownload = !audio.audioData && !!audio.audioUrl;
            const safeTitle = escapeHtml(getAudiobookDisplayTitle(audio.title));
            item.innerHTML = `
                <div class="audio-item-bg" data-action="delete" data-id="${audio.id}"><i data-lucide="trash-2"></i></div>
                <div class="audio-item-front">
                    <div class="audio-title-group"><i data-lucide="play-circle"></i><span class="audio-title" title="${safeTitle}">${safeTitle}</span>${audio.isDefault ? '<span class="default-badge" title="기본 제공 오디오북">기본 제공</span>' : ""}</div>
                    <div class="audio-actions"><button class="btn-icon-round btn-more" data-id="${audio.id}" title="더보기"><i data-lucide="more-horizontal"></i></button></div>
                </div>`;
            const front = item.querySelector(".audio-item-front");
            const bg = item.querySelector(".audio-item-bg");
            let startX = 0;
            let startY = 0;
            let currentX = 0;
            let isDragging = false;
            let isSwipe = false;
            front.addEventListener("touchstart", (event) => {
                startX = event.touches[0].clientX;
                startY = event.touches[0].clientY;
                currentX = startX;
                isDragging = true;
                isSwipe = false;
                front.classList.add("ui-dragging");
            }, { passive: true });
            front.addEventListener("touchmove", (event) => {
                if (!isDragging) return;
                const x = event.touches[0].clientX;
                const y = event.touches[0].clientY;
                const deltaX = x - startX;
                const deltaY = y - startY;
                if (!isSwipe) {
                    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 5) isSwipe = true;
                    else if (Math.abs(deltaY) > 5) {
                        isDragging = false;
                        front.classList.remove("ui-dragging");
                        return;
                    }
                }
                if (!isSwipe) return;
                if (event.cancelable) event.preventDefault();
                currentX = x;
                if (deltaX < 0) {
                    bg.style.display = "";
                    front.style.transform = `translateX(${deltaX}px)`;
                } else if (deltaX > 0) {
                    bg.style.display = "none";
                    front.style.transform = `translateX(${deltaX * 0.15}px)`;
                }
            }, { passive: false });
            front.addEventListener("touchend", () => {
                if (!isDragging) return;
                isDragging = false;
                front.classList.remove("ui-dragging");
                const deltaX = currentX - startX;
                if (deltaX < -150) {
                    if (navigator.vibrate) navigator.vibrate(50);
                    if (confirm("정말 이 오디오북을 삭제하시겠습니까?")) {
                        front.classList.add("deleting");
                        item.classList.add("deleting-row");
                        setTimeout(() => deleteAudiobook(audio.id), 350);
                    } else {
                        front.style.transform = "";
                        item.classList.remove("swipe-open");
                    }
                } else if (deltaX < -40) {
                    front.style.transform = "translateX(-80px)";
                    item.classList.add("swipe-open");
                } else {
                    front.style.transform = "";
                    item.classList.remove("swipe-open");
                }
            }, { passive: true });
            document.addEventListener("touchstart", (event) => {
                if (item.classList.contains("swipe-open") && !item.contains(event.target)) {
                    front.style.transform = "";
                    item.classList.remove("swipe-open");
                }
            }, { passive: true });
            bg.addEventListener("click", (event) => {
                event.stopPropagation();
                if (confirm("정말 이 오디오북을 삭제하시겠습니까?")) deleteAudiobook(audio.id);
            });
            if (hasSentences || needsDownload) {
                item.addEventListener("click", async (event) => {
                    if (item.classList.contains("swipe-open")) {
                        front.style.transform = "";
                        item.classList.remove("swipe-open");
                        return;
                    }
                    if (event.target.closest(".btn-more")) return;
                    let freshAudio = await getAudiobookFromDB(audio.id);
                    if (!freshAudio) {
                        showToast("오디오 데이터를 불러올 수 없습니다. 다시 생성해 주세요.", "error");
                        return;
                    }
                    if (!freshAudio.audioData && freshAudio.audioUrl) {
                        showToast("클라우드에서 불러오는 중...", "info");
                        try {
                            freshAudio = await ensureAudioData(freshAudio);
                        } catch (error) {
                            console.error(error);
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
            item.querySelector(".btn-more").addEventListener("click", (event) => {
                event.stopPropagation();
                openActionSheet(audio);
            });
            audioList.appendChild(item);
        }

        async function uploadAudiobookToCloud(entry) {
            const res = await fetch("/api/audiobooks", {
                method: "POST",
                headers: { ...authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ title: entry.title, file_name: entry.title, duration_seconds: entry.durationSeconds || null }),
            });
            if (!res.ok) throw new Error("클라우드 등록 실패");
            const { id, audio_upload, sentences_upload } = await res.json();
            const up = await fetch(audio_upload.signed_url, {
                method: "PUT", headers: { "Content-Type": "audio/mpeg" }, body: entry.audioData,
            });
            if (!up.ok) throw new Error("오디오 업로드 실패");
            await fetch(sentences_upload.signed_url, {
                method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(entry.sentences || []),
            });
            return id;
        }

        async function ensureAudioData(entry) {
            if (entry.audioData || !entry.audioUrl) return entry;
            const [audioRes, sentRes] = await Promise.all([
                fetch(entry.audioUrl), entry.sentencesUrl ? fetch(entry.sentencesUrl) : Promise.resolve(null),
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
                const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, { headers: authHeaders() });
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
            } catch (error) {
                console.error("재생 상태 동기화 실패:", error);
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
                }),
            });
            if (!res.ok) throw new Error("재생 상태 저장 실패");
            const state = await res.json();
            entry.playbackUpdatedAt = Date.parse(state.updated_at || state.last_played_at || "") || Date.now();
            await saveAudiobookToDB(entry);
        }

        async function sync({ silent = false } = {}) {
            const result = { uploaded: 0, added: 0, failed: 0, deleted: 0, ok: false };
            if (!isLoggedIn() || syncing) return result;
            syncing = true;
            try {
                const res = await fetch("/api/audiobooks", { headers: authHeaders() });
                if (!res.ok) return result;
                const cloud = (await res.json()).audiobooks || [];
                const local = await getAllAudiobooksFromDB();
                const cloudIds = new Set(cloud.map(item => item.id));
                for (const item of local) {
                    if (!item.isDefault && item.cloudId && !cloudIds.has(item.cloudId)) {
                        await deleteAudiobookFromDB(item.id);
                        result.deleted++;
                    }
                }
                for (const item of local) {
                    if (item.isDefault || !item.audioData || (item.cloudId && cloudIds.has(item.cloudId)) || (item.cloudId && !cloudIds.has(item.cloudId))) continue;
                    try {
                        const cloudId = await uploadAudiobookToCloud(item);
                        await saveAudiobookToDB({ ...item, cloudId });
                        result.uploaded++;
                    } catch (error) {
                        console.error("업로드 실패:", item.title, error);
                        result.failed++;
                    }
                }
                const localByCloudId = new Map(local.filter(item => item.cloudId).map(item => [item.cloudId, item]));
                for (const cloudEntry of cloud) {
                    const existing = localByCloudId.get(cloudEntry.id);
                    if (existing) {
                        const refreshed = await fetchPlaybackState({
                            ...existing,
                            title: cloudEntry.title || cloudEntry.file_name || existing.title,
                            audioUrl: cloudEntry.audio_url,
                            sentencesUrl: cloudEntry.sentences_url,
                        });
                        await saveAudiobookToDB(refreshed);
                        continue;
                    }
                    const timestamp = Date.parse(cloudEntry.created_at) || Date.now();
                    const added = {
                        id: cloudEntry.id, cloudId: cloudEntry.id,
                        title: cloudEntry.title || cloudEntry.file_name || "제목 없음",
                        audioData: null, sentences: [], audioUrl: cloudEntry.audio_url, sentencesUrl: cloudEntry.sentences_url,
                        cloudOnly: true, timestamp,
                        dateString: new Date(timestamp).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }),
                        sizeBytes: 0, charCount: 0,
                    };
                    await saveAudiobookToDB(await fetchPlaybackState(added));
                    result.added++;
                }
                result.ok = result.failed === 0;
                if (result.uploaded || result.added) {
                    render();
                    if (!silent) showToast(`동기화 완료 (올림 ${result.uploaded}, 받음 ${result.added})`, "success");
                }
                return result;
            } catch (error) {
                console.error("클라우드 동기화 실패:", error);
                return result;
            } finally {
                syncing = false;
            }
        }

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

        function closeActionSheetIfOpen() {
            if (!actionSheetBackdrop.classList.contains("show")) return false;
            closeActionSheet();
            return true;
        }

        async function performShare(target) {
            try {
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
                    } catch (error) {
                        console.log("Server check failed, will re-upload", error);
                    }
                }
                if (needsUpload) {
                    showToast("서버에 업로드하여 공유 링크 생성 중...", "info");
                    const audioBlob = freshAudio.audioData instanceof Blob
                        ? freshAudio.audioData : new Blob([freshAudio.audioData], { type: "audio/mpeg" });
                    const formData = new FormData();
                    formData.append("audio", audioBlob, "audio.mp3");
                    formData.append("title", target.title);
                    formData.append("sentences", JSON.stringify(freshAudio.sentences || []));
                    const response = await fetch("/api/share", { method: "POST", headers: authHeaders(), body: formData });
                    if (!response.ok) throw new Error("서버 업로드 실패");
                    const result = await response.json();
                    share_id = result.share_id;
                    freshAudio.shareId = share_id;
                    freshAudio.shareExpiry = now + (23 * 60 * 60 * 1000) + (50 * 60 * 1000);
                    await saveAudiobookToDB(freshAudio);
                }
                const shareUrl = `${window.location.origin}/share/${share_id}`;
                if (navigator.share) {
                    await navigator.share({ title: target.title, text: `"${target.title}" - TextAudio 오디오북을 들어보세요`, url: shareUrl });
                } else {
                    try {
                        await navigator.clipboard.writeText(shareUrl);
                        showToast("공유 링크가 복사되었습니다! (24시간 유효)", "success");
                    } catch (clipErr) {
                        prompt("브라우저 보안 설정으로 자동 복사가 제한되었습니다. 아래 링크를 복사하세요:", shareUrl);
                    }
                }
            } catch (error) {
                if (error.name !== "AbortError") {
                    console.log("Share failed:", error);
                    showToast("공유에 실패했습니다.", "error");
                }
            }
        }

        async function downloadAudiobook(target) {
            try {
                const freshAudio = await getAudiobookFromDB(target.id);
                if (!freshAudio || !freshAudio.audioData) {
                    showToast("오디오 데이터를 찾을 수 없습니다.", "error");
                    return;
                }
                const audioBlob = freshAudio.audioData instanceof Blob
                    ? freshAudio.audioData : new Blob([freshAudio.audioData], { type: "audio/mpeg" });
                const url = URL.createObjectURL(audioBlob);
                const link = document.createElement("a");
                link.style.display = "none";
                link.href = url;
                let filename = target.title || "audiobook";
                if (!filename.toLowerCase().endsWith(".mp3")) filename += ".mp3";
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                setTimeout(() => {
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                }, 100);
                showToast("다운로드가 시작되었습니다.", "success");
            } catch (error) {
                console.error("Download error:", error);
                showToast("다운로드에 실패했습니다.", "error");
            }
        }

        async function editAudiobookTitle(target) {
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
                        method: "PATCH", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ title: nextTitle }),
                    });
                    if (!res.ok) throw new Error("제목 수정 실패");
                }
                await saveAudiobookToDB({ ...target, title: nextTitle });
                render();
                showToast("제목을 수정했습니다.", "success");
            } catch (error) {
                console.error(error);
                showToast("제목을 수정하지 못했습니다.", "error");
            }
        }

        async function deleteAudiobook(id) {
            try {
                const entry = await getAudiobookFromDB(id);
                if (entry && entry.cloudId && isLoggedIn()) {
                    try {
                        await fetch(`/api/audiobooks/${entry.cloudId}`, { method: "DELETE", headers: authHeaders() });
                    } catch (error) {
                        console.error("클라우드 삭제 실패:", error);
                    }
                }
                await deleteAudiobookFromDB(id);
                if (objectUrls[id]) {
                    URL.revokeObjectURL(objectUrls[id]);
                    delete objectUrls[id];
                }
                render();
                showToast("제거되었습니다.", "info");
            } catch (error) {
                console.error(error);
                showToast("제거 실패", "error");
            }
        }

        function initialize() {
            if (initialized) return;
            initialized = true;
            actionCancelBtn.addEventListener("click", closeActionSheet);
            actionSheetBackdrop.addEventListener("click", (event) => {
                if (event.target === actionSheetBackdrop) closeActionSheet();
            });
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
                await downloadAudiobook(target);
            });
            actionEditTitleBtn.addEventListener("click", async () => {
                if (!actionSheetTarget || actionSheetTarget.isDefault) return;
                const target = actionSheetTarget;
                closeActionSheet();
                await editAudiobookTitle(target);
            });
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
            if (readerShareBtn) {
                readerShareBtn.addEventListener("click", async () => {
                    const currentAudio = getCurrentAudio();
                    if (currentAudio) await performShare(currentAudio);
                });
            }
            window.__syncAudiobooksToCloud = sync;
            window.__renderLibrary = render;
        }

        function load() {
            render();
            seedDefaultBookIfNeeded();
            if (isLoggedIn()) sync();
        }

        return { initialize, load, render, sync, savePlaybackState, closeActionSheetIfOpen };
    };
})();
