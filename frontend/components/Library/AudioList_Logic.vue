<script lang="ts">
import {
    getAllAudiobooksFromDB,
    saveAudiobookToDB,
    deleteAudiobookFromDB,
    getAudiobookFromDB,
    type AudiobookRecord,
} from "../../services/indexedDb";
import { getAudiobookDisplayTitle } from "../../utils/format";
import { useAuthLogic } from "../../Auth/Auth_Logic.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";
import type { AudioListState, BackgroundJobItem } from "./AudioList_State.vue";

export interface SyncResult {
    uploaded: number;
    added: number;
    failed: number;
    deleted: number;
    ok: boolean;
}

export interface AudioListLogic {
    refresh(): Promise<void>;
    load(): Promise<void>;
    openItem(audio: AudiobookRecord): Promise<void>;
    openActionSheet(audio: AudiobookRecord): void;
    closeActionSheet(): void;
    performShare(target: AudiobookRecord): Promise<void>;
    downloadAudiobook(target: AudiobookRecord): Promise<void>;
    editAudiobookTitle(target: AudiobookRecord): Promise<void>;
    toggleBookmark(target: AudiobookRecord): Promise<void>;
    moveToFolder(target: AudiobookRecord, folderId: string | null): Promise<boolean>;
    deleteAudiobook(id: string): Promise<void>;
    sync(options?: { silent?: boolean }): Promise<SyncResult>;
    savePlaybackState(entry: AudiobookRecord, position: number, playbackSettings: { playbackSpeed: number; repeatMode: string }): Promise<void>;
    showBackgroundJob(jobId: string, title?: string): void;
    removeBackgroundJob(jobId: string): void;
}

const DEFAULT_BOOK_ID = "default-sherlock-holmes";
let syncing = false;

// static/js/library.js를 옮긴 것. 스와이프/터치 제스처는 각 항목을 맡는
// AudioListItem_View.vue가 담당하고, 이 파일은 데이터 조작(조회/공유/
// 다운로드/제목수정/삭제/클라우드 동기화/기본 제공 도서 시딩)을 맡는다.
// 항목을 열 때는 window.__openReaderMode 훅(Reader_Logic이 등록)을 호출한다.
export function useAudioListLogic(state: AudioListState): AudioListLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    async function refresh(): Promise<void> {
        try {
            state.savedAudiobooks.value = await getAllAudiobooksFromDB();
        } catch (error) {
            console.error("Library render error: ", error);
            showToast("보관함을 불러올 수 없습니다.", "error");
        }
    }

    async function seedDefaultBookIfNeeded(): Promise<void> {
        try {
            const existing = await getAudiobookFromDB(DEFAULT_BOOK_ID);
            let needsUpdate = false;
            let meta: any = null;
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
            } catch {
                if (!existing || !existing.audioData) needsUpdate = true;
            }
            if (!needsUpdate) return;

            let attempts = 0;
            while (attempts < 60 && (!meta || meta.status !== "ready")) {
                try {
                    const metaRes = await fetch("/api/default-book");
                    if (!metaRes.ok) {
                        attempts++;
                        await new Promise((resolve) => setTimeout(resolve, 2000));
                        continue;
                    }
                    meta = await metaRes.json();
                    if (meta.status === "ready") break;
                    if (meta.status === "error") console.warn("Default book generation error on server:", meta.error);
                } catch (fetchError) {
                    console.warn("Error fetching default book status:", fetchError);
                }
                await new Promise((resolve) => setTimeout(resolve, 2000));
                attempts++;
            }
            if (!meta || meta.status !== "ready") {
                showToast("기본 제공 오디오북을 준비할 수 없습니다. 새 문서를 업로드해 주세요.", "info");
                return;
            }
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
                await refresh();
                showToast("기본 제공 오디오북이 준비되었습니다!", "success");
            } catch (innerError) {
                console.error("Failed to save default book:", innerError);
                showToast("기본 제공 오디오북 저장에 실패했습니다.", "error");
            }
        } catch (error) {
            console.error("Default book sync failed:", error);
        }
    }

    async function uploadAudiobookToCloud(entry: AudiobookRecord): Promise<string> {
        const res = await fetch("/api/audiobooks", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                title: entry.title, file_name: entry.title, duration_seconds: null,
                folder_id: entry.folderId ?? null,
            }),
        });
        if (!res.ok) throw new Error("클라우드 등록 실패");
        const { id, audio_upload, sentences_upload } = await res.json();
        const up = await fetch(audio_upload.signed_url, {
            method: "PUT", headers: { "Content-Type": "audio/mpeg" }, body: entry.audioData as BodyInit,
        });
        if (!up.ok) throw new Error("오디오 업로드 실패");
        await fetch(sentences_upload.signed_url, {
            method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(entry.sentences || []),
        });
        return id;
    }

    async function ensureAudioData(entry: AudiobookRecord): Promise<AudiobookRecord> {
        if (entry.audioData || !entry.audioUrl) return entry;
        const [audioRes, sentRes] = await Promise.all([
            fetch(entry.audioUrl), entry.sentencesUrl ? fetch(entry.sentencesUrl) : Promise.resolve(null),
        ]);
        if (!audioRes.ok) throw new Error("오디오 다운로드 실패");
        const buffer = await audioRes.arrayBuffer();
        let sentences = entry.sentences || [];
        if (sentRes && sentRes.ok) {
            try { sentences = await sentRes.json(); } catch { /* 자막 없이도 재생은 된다 */ }
        }
        const filled = { ...entry, audioData: buffer, sentences, sizeBytes: buffer.byteLength, cloudOnly: false };
        await saveAudiobookToDB(filled);
        return filled;
    }

    async function fetchPlaybackState(entry: AudiobookRecord): Promise<AudiobookRecord> {
        if (!entry.cloudId || !authLogic.isLoggedIn()) return entry;
        try {
            const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, { headers: authLogic.authHeaders() });
            if (!res.ok) return entry;
            const playbackState = await res.json();
            const updatedAt = Date.parse(playbackState.updated_at || playbackState.last_played_at || "") || 0;
            if (updatedAt <= (entry.playbackUpdatedAt || 0)) return entry;
            const synced: AudiobookRecord = {
                ...entry,
                lastPosition: playbackState.current_time_seconds || 0,
                playbackSpeed: playbackState.playback_speed || 1.0,
                repeatMode: playbackState.repeat_mode || "off",
                playbackUpdatedAt: updatedAt,
            };
            await saveAudiobookToDB(synced);
            return synced;
        } catch (error) {
            console.error("재생 상태 동기화 실패:", error);
            return entry;
        }
    }

    async function savePlaybackState(entry: AudiobookRecord, position: number, playbackSettings: { playbackSpeed: number; repeatMode: string }): Promise<void> {
        if (!entry.cloudId || !authLogic.isLoggedIn()) return;
        const res = await fetch(`/api/audiobooks/${entry.cloudId}/playback`, {
            method: "PUT",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                current_time_seconds: position,
                playback_speed: entry.playbackSpeed || playbackSettings.playbackSpeed,
                repeat_mode: entry.repeatMode || playbackSettings.repeatMode,
            }),
        });
        if (!res.ok) throw new Error("재생 상태 저장 실패");
        const playbackState = await res.json();
        entry.playbackUpdatedAt = Date.parse(playbackState.updated_at || playbackState.last_played_at || "") || Date.now();
        await saveAudiobookToDB(entry);
    }

    async function sync({ silent = false }: { silent?: boolean } = {}): Promise<SyncResult> {
        const result: SyncResult = { uploaded: 0, added: 0, failed: 0, deleted: 0, ok: false };
        if (!authLogic.isLoggedIn() || syncing) return result;
        syncing = true;
        try {
            const res = await fetch("/api/audiobooks", { headers: authLogic.authHeaders() });
            if (!res.ok) return result;
            const cloud = ((await res.json()).audiobooks || []) as any[];
            const local = await getAllAudiobooksFromDB();
            const cloudIds = new Set(cloud.map((item) => item.id));
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
            const localByCloudId = new Map(local.filter((item) => item.cloudId).map((item) => [item.cloudId, item]));
            for (const cloudEntry of cloud) {
                const existing = localByCloudId.get(cloudEntry.id);
                if (existing) {
                    const refreshed = await fetchPlaybackState({
                        ...existing,
                        title: cloudEntry.title || cloudEntry.file_name || existing.title,
                        audioUrl: cloudEntry.audio_url,
                        sentencesUrl: cloudEntry.sentences_url,
                        folderId: cloudEntry.folder_id ?? null,
                        isBookmarked: !!cloudEntry.is_bookmarked,
                    });
                    await saveAudiobookToDB(refreshed);
                    continue;
                }
                const timestamp = Date.parse(cloudEntry.created_at) || Date.now();
                const added: AudiobookRecord = {
                    id: cloudEntry.id, cloudId: cloudEntry.id,
                    title: cloudEntry.title || cloudEntry.file_name || "제목 없음",
                    audioData: null, sentences: [], audioUrl: cloudEntry.audio_url, sentencesUrl: cloudEntry.sentences_url,
                    cloudOnly: true, timestamp,
                    dateString: new Date(timestamp).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }),
                    sizeBytes: 0, charCount: 0,
                    folderId: cloudEntry.folder_id ?? null,
                    isBookmarked: !!cloudEntry.is_bookmarked,
                };
                await saveAudiobookToDB(await fetchPlaybackState(added));
                result.added++;
            }
            result.ok = result.failed === 0;
            if (result.uploaded || result.added) {
                await refresh();
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

    function openActionSheet(audio: AudiobookRecord): void {
        state.actionSheetTarget.value = audio;
        state.isActionSheetOpen.value = true;
    }

    function closeActionSheet(): void {
        state.isActionSheetOpen.value = false;
        state.actionSheetTarget.value = null;
    }

    async function openItem(audio: AudiobookRecord): Promise<void> {
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
        (window as any).__openReaderMode?.(freshAudio);
    }

    async function performShare(target: AudiobookRecord): Promise<void> {
        try {
            const freshAudio = await getAudiobookFromDB(target.id);
            if (!freshAudio || !freshAudio.audioData) {
                showToast("오디오 데이터를 찾을 수 없습니다.", "error");
                return;
            }
            let shareId = freshAudio.shareId;
            const now = Date.now();
            let needsUpload = true;
            if (freshAudio.id === "default_book") {
                shareId = "default_book";
                needsUpload = false;
            } else if (shareId && freshAudio.shareExpiry && freshAudio.shareExpiry > now) {
                try {
                    const checkRes = await fetch(`/api/share/${shareId}`);
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
                    ? freshAudio.audioData : new Blob([freshAudio.audioData as ArrayBuffer], { type: "audio/mpeg" });
                const formData = new FormData();
                formData.append("audio", audioBlob, "audio.mp3");
                formData.append("title", target.title);
                formData.append("sentences", JSON.stringify(freshAudio.sentences || []));
                const response = await fetch("/api/share", { method: "POST", headers: authLogic.authHeaders(), body: formData });
                if (!response.ok) throw new Error("서버 업로드 실패");
                const result = await response.json();
                shareId = result.share_id;
                freshAudio.shareId = shareId;
                freshAudio.shareExpiry = now + (23 * 60 * 60 * 1000) + (50 * 60 * 1000);
                await saveAudiobookToDB(freshAudio);
            }
            const shareUrl = `${window.location.origin}/share/${shareId}`;
            if (navigator.share) {
                await navigator.share({ title: target.title, text: `"${target.title}" - TextAudio 오디오북을 들어보세요`, url: shareUrl });
            } else {
                try {
                    await navigator.clipboard.writeText(shareUrl);
                    showToast("공유 링크가 복사되었습니다! (24시간 유효)", "success");
                } catch {
                    window.prompt("브라우저 보안 설정으로 자동 복사가 제한되었습니다. 아래 링크를 복사하세요:", shareUrl);
                }
            }
        } catch (error) {
            if ((error as Error).name !== "AbortError") {
                console.log("Share failed:", error);
                showToast("공유에 실패했습니다.", "error");
            }
        }
    }

    async function downloadAudiobook(target: AudiobookRecord): Promise<void> {
        try {
            const freshAudio = await getAudiobookFromDB(target.id);
            if (!freshAudio || !freshAudio.audioData) {
                showToast("오디오 데이터를 찾을 수 없습니다.", "error");
                return;
            }
            const audioBlob = freshAudio.audioData instanceof Blob
                ? freshAudio.audioData : new Blob([freshAudio.audioData as ArrayBuffer], { type: "audio/mpeg" });
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

    async function editAudiobookTitle(target: AudiobookRecord): Promise<void> {
        const title = window.prompt("오디오북 제목", getAudiobookDisplayTitle(target.title));
        if (title === null) return;
        const nextTitle = title.trim();
        if (!nextTitle) {
            showToast("제목을 입력해 주세요.", "error");
            return;
        }
        try {
            if (target.cloudId && authLogic.isLoggedIn()) {
                const res = await fetch(`/api/audiobooks/${target.cloudId}`, {
                    method: "PATCH", headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ title: nextTitle }),
                });
                if (!res.ok) throw new Error("제목 수정 실패");
            }
            await saveAudiobookToDB({ ...target, title: nextTitle });
            await refresh();
            showToast("제목을 수정했습니다.", "success");
        } catch (error) {
            console.error(error);
            showToast("제목을 수정하지 못했습니다.", "error");
        }
    }

    async function toggleBookmark(target: AudiobookRecord): Promise<void> {
        if (!target.cloudId || !authLogic.isLoggedIn()) {
            showToast("즐겨찾기는 로그인 후 이용할 수 있습니다.", "info");
            return;
        }
        const nextValue = !target.isBookmarked;
        try {
            const res = await fetch(`/api/audiobooks/${target.cloudId}`, {
                method: "PATCH",
                headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ is_bookmarked: nextValue }),
            });
            if (!res.ok) throw new Error("즐겨찾기 변경 실패");
            await saveAudiobookToDB({ ...target, isBookmarked: nextValue });
            await refresh();
        } catch (error) {
            console.error(error);
            showToast("즐겨찾기 변경에 실패했습니다.", "error");
        }
    }

    async function moveToFolder(target: AudiobookRecord, folderId: string | null): Promise<boolean> {
        if (!target.cloudId || !authLogic.isLoggedIn()) {
            showToast("폴더 이동은 로그인 후 이용할 수 있습니다.", "info");
            return false;
        }
        try {
            const res = await fetch(`/api/audiobooks/${target.cloudId}`, {
                method: "PATCH",
                headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ folder_id: folderId }),
            });
            if (!res.ok) throw new Error("폴더 이동 실패");
            await saveAudiobookToDB({ ...target, folderId });
            await refresh();
            return true;
        } catch (error) {
            console.error(error);
            showToast("폴더 이동에 실패했습니다.", "error");
            return false;
        }
    }

    async function deleteAudiobook(id: string): Promise<void> {
        try {
            const entry = await getAudiobookFromDB(id);
            if (entry && entry.cloudId && authLogic.isLoggedIn()) {
                try {
                    await fetch(`/api/audiobooks/${entry.cloudId}`, { method: "DELETE", headers: authLogic.authHeaders() });
                } catch (error) {
                    console.error("클라우드 삭제 실패:", error);
                }
            }
            await deleteAudiobookFromDB(id);
            await refresh();
            showToast("제거되었습니다.", "info");
        } catch (error) {
            console.error(error);
            showToast("제거 실패", "error");
        }
    }

    async function load(): Promise<void> {
        await refresh();
        await seedDefaultBookIfNeeded();
        if (authLogic.isLoggedIn()) await sync();
    }

    // notifications.js가 백그라운드(대용량) 생성 작업을 페이지 재방문 시
    // 이어서 보여줄 때 쓰는 훅 — generation-status.js의 show/remove에 대응.
    function showBackgroundJob(jobId: string, title = "오디오북", folderId: string | null = null): void {
        if (state.backgroundJobItems.value.some((item) => item.jobId === jobId)) return;
        state.backgroundJobItems.value = [...state.backgroundJobItems.value, { jobId, title, folderId }];
    }

    function removeBackgroundJob(jobId: string): void {
        state.backgroundJobItems.value = state.backgroundJobItems.value.filter((item) => item.jobId !== jobId);
    }

    (window as any).__renderLibrary = refresh;
    (window as any).__syncAudiobooksToCloud = sync;
    (window as any).__showBackgroundJobLoading = showBackgroundJob;
    (window as any).__removeBackgroundJobLoading = removeBackgroundJob;

    return {
        refresh, load, openItem, openActionSheet, closeActionSheet,
        performShare, downloadAudiobook, editAudiobookTitle, toggleBookmark, moveToFolder, deleteAudiobook, sync,
        savePlaybackState, showBackgroundJob, removeBackgroundJob,
    };
}

export default {};
</script>
