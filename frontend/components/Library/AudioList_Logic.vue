<script lang="ts">
import {
    getAllAudiobooksFromDB,
    saveAudiobookToDB,
    deleteAudiobookFromDB,
    getAudiobookFromDB,
    DEFAULT_BOOK_ID,
    DEFAULT_BOOK_DISMISSED_KEY,
    type AudiobookRecord,
} from "../../services/indexedDb";
import { getAudiobookDisplayTitle } from "../../utils/format";
import { useAuthLogic } from "../../Auth/Auth_Logic.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";
import { usePromptSheetLogic } from "../../Sheet/PromptSheet_Logic.vue";
import { usePromptSheetState } from "../../Sheet/PromptSheet_State.vue";
import type { AudioListState, BackgroundJobItem } from "./AudioList_State.vue";
import { streamJobAudio } from "../../services/progressiveAudio";
import { reportClientError } from "../../services/clientErrors";

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
    showBackgroundJob(jobId: string, title?: string, folderId?: string | null): void;
    removeBackgroundJob(jobId: string): void;
    listenEarlyToBackgroundJob(jobId: string): Promise<void>;
}

let syncing = false;

// static/js/library.js를 옮긴 것. 스와이프/터치 제스처는 각 항목을 맡는
// AudioListItem_View.vue가 담당하고, 이 파일은 데이터 조작(조회/공유/
// 다운로드/제목수정/삭제/클라우드 동기화/기본 제공 도서 시딩)을 맡는다.
// 항목을 열 때는 window.__openReaderMode 훅(Reader_Logic이 등록)을 호출한다.
export function useAudioListLogic(state: AudioListState): AudioListLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());
    const { showPrompt } = usePromptSheetLogic(usePromptSheetState());

    async function refresh(): Promise<void> {
        try {
            state.savedAudiobooks.value = await getAllAudiobooksFromDB();
        } catch (error) {
            console.error("Library render error: ", error);
            showToast("보관함을 불러올 수 없습니다.", "error");
        } finally {
            state.loaded.value = true;
        }
    }

    async function seedDefaultBookIfNeeded(): Promise<void> {
        // 로그인 사용자가 서재에서 직접 지운 적이 있으면 다시 채워 넣지
        // 않는다 — 로그아웃 시(Auth_Logic.vue) 이 표시를 지워서 다음
        // 방문자에게는 다시 보이게 한다.
        if (localStorage.getItem(DEFAULT_BOOK_DISMISSED_KEY) === "1") return;
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
                reportClientError("default_book", innerError);
                console.error("Failed to save default book:", innerError);
                showToast("기본 제공 오디오북 저장에 실패했습니다.", "error");
            }
        } catch (error) {
            reportClientError("default_book", error);
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

    /** 재생을 막지 않고 뒤에서 본체를 받아 둔다. 다음부터는 오프라인에서도 열린다. */
    function cacheAudioInBackground(entry: AudiobookRecord, audioUrl: string): void {
        (async () => {
            try {
                const response = await fetch(audioUrl);
                if (!response.ok) return;
                const buffer = await response.arrayBuffer();
                // 받는 사이에 사용자가 지웠을 수 있다. 지운 것을 되살리면 안 된다.
                const stillThere = await getAudiobookFromDB(entry.id);
                if (!stillThere) return;
                await saveAudiobookToDB({
                    ...stillThere, audioData: buffer, sizeBytes: buffer.byteLength, cloudOnly: false,
                });
            } catch (error) {
                // 캐시는 부수적이다 — 실패해도 지금 재생은 원격 URL로 멀쩡히 돌아간다.
                reportClientError("cloud_sync", error);
            }
        })();
    }

    /** 스트리밍으로 곧바로 틀 수 있게 준비한다. 문장(작은 JSON)만 기다린다. */
    async function prepareStreaming(entry: AudiobookRecord): Promise<AudiobookRecord> {
        // ⚠️ 저장해 둔 audio_url은 목록을 받을 때 서명한 것이라 한 시간 뒤 죽는다.
        // PWA는 며칠씩 열려 있으므로 재생 직전에 새로 받는다 — 경제 뉴스가
        // 정확히 이 방식으로 404가 났었다.
        let audioUrl = entry.audioUrl;
        let sentencesUrl = entry.sentencesUrl;
        if (entry.cloudId && authLogic.isLoggedIn()) {
            try {
                const response = await fetch(`/api/audiobooks/${entry.cloudId}/media-urls`, {
                    headers: authLogic.authHeaders(),
                });
                if (response.ok) {
                    const fresh = await response.json();
                    audioUrl = fresh.audio_url || audioUrl;
                    sentencesUrl = fresh.sentences_url || sentencesUrl;
                }
            } catch {
                // 갱신에 실패하면 저장해 둔 URL로 시도한다 — 아직 살아 있을 수 있다.
            }
        }
        if (!audioUrl) throw new Error("오디오 주소가 없습니다.");

        let sentences = entry.sentences || [];
        if (sentencesUrl && sentences.length === 0) {
            try {
                const response = await fetch(sentencesUrl);
                if (response.ok) sentences = await response.json();
            } catch {
                // 문장이 없어도 재생은 된다. 하이라이트만 안 될 뿐이다.
            }
        }

        cacheAudioInBackground(entry, audioUrl);
        return { ...entry, audioUrl, sentencesUrl, sentences };
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
            reportClientError("playback_save", error);
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
                    reportClientError("cloud_sync", error);
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
            reportClientError("cloud_sync", error);
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
        if (!freshAudio.audioData) {
            // 오디오 본체는 기다리지 않는다. 문장(작은 JSON)만 받아 곧바로
            // 재생을 시작하고, MP3는 원격 URL에서 스트리밍한다 — 예전에는
            // 20MB를 다 받고서야 리더가 열려 첫 재생이 오래 걸렸다.
            try {
                freshAudio = await prepareStreaming(freshAudio);
            } catch (error) {
                console.error(error);
                showToast("클라우드에서 오디오를 받지 못했습니다.", "error");
                return;
            }
        }
        if (!freshAudio.audioData && !freshAudio.audioUrl) {
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
                    showPrompt("아래 링크를 복사하세요", { subtitle: "브라우저 보안 설정으로 자동 복사가 제한되었습니다", defaultValue: shareUrl });
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
        const title = await showPrompt("오디오북 제목", { defaultValue: getAudiobookDisplayTitle(target.title) });
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
            // 다음 load()에서 seedDefaultBookIfNeeded()가 다시 채워 넣지
            // 않도록 표시해 둔다.
            if (id === DEFAULT_BOOK_ID) localStorage.setItem(DEFAULT_BOOK_DISMISSED_KEY, "1");
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

    /** 백그라운드로 도는 작업의 앞 구간을 받아 듣는다.
     *
     * 서버는 백그라운드 작업에도 준비된 청크를 그대로 내준다(ready_chunks).
     * 그런데 그걸 받아 오는 코드가 모달을 켜둔 포그라운드 경로에만 붙어 있어,
     * 앱을 나갔다 오면 합성이 끝날 때까지 아무것도 들을 수 없었다 — 정작
     * 기다림이 가장 긴 문서(스캔본 등)가 전부 이쪽으로 온다.
     *
     * 자동으로 받지 않고 누른 뒤에 받는다. 이 경로의 문서는 길어서, 들을지
     * 모르는 오디오를 미리 통째로 내려받으면 데이터가 아깝다.
     */
    async function listenEarlyToBackgroundJob(jobId: string): Promise<void> {
        const find = () => state.backgroundJobItems.value.find((entry) => entry.jobId === jobId);

        const started = find();
        if (!started || started.isPreparingPreview) return;
        // 이미 받아 둔 게 있으면 그걸로 바로 연다.
        if (started.playableAudio) {
            openPartialReader(started);
            return;
        }
        patchBackgroundJob(jobId, { isPreparingPreview: true });

        let opened = false;
        try {
            await streamJobAudio(jobId, authLogic.authHeaders(), {
                onPlayable(blob, sentences) {
                    // 목록에서 사라졌으면(완료·삭제) 더 붙들지 않는다.
                    if (!find()) return;
                    patchBackgroundJob(jobId, {
                        playableAudio: blob,
                        playableSentences: sentences,
                        isPreparingPreview: false,
                    });
                    // 처음 들을 수 있게 된 순간 한 번만 연다. 이후로도 계속
                    // 받아 두어, 닫았다 다시 누르면 더 긴 구간이 열린다.
                    if (!opened) {
                        opened = true;
                        openPartialReader(find()!);
                    }
                },
            });
        } catch (error) {
            reportClientError("generation", error);
            if (!opened) showToast("아직 들을 수 있는 구간이 없습니다.", "error");
        } finally {
            patchBackgroundJob(jobId, { isPreparingPreview: false });
        }
    }

    function patchBackgroundJob(jobId: string, patch: Partial<BackgroundJobItem>): void {
        state.backgroundJobItems.value = state.backgroundJobItems.value.map((entry) =>
            entry.jobId === jobId ? { ...entry, ...patch } : entry
        );
    }

    function openPartialReader(item: BackgroundJobItem): void {
        if (!item.playableAudio) return;
        const url = URL.createObjectURL(item.playableAudio);
        (window as any).__openPartialReaderMode?.(item.title, item.playableSentences ?? [], url);
    }

    (window as any).__renderLibrary = refresh;
    (window as any).__syncAudiobooksToCloud = sync;
    (window as any).__showBackgroundJobLoading = showBackgroundJob;
    (window as any).__removeBackgroundJobLoading = removeBackgroundJob;

    return {
        refresh, load, openItem, openActionSheet, closeActionSheet,
        performShare, downloadAudiobook, editAudiobookTitle, toggleBookmark, moveToFolder, deleteAudiobook, sync,
        savePlaybackState, showBackgroundJob, removeBackgroundJob, listenEarlyToBackgroundJob,
    };
}

export default {};
</script>
