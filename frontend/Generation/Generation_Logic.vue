<script lang="ts">
import { useAuthStore } from "../stores/auth";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { reportClientError } from "../services/clientErrors";
import { useToastState } from "../components/Toast/Toast_State.vue";
import { saveAudiobookToDB } from "../services/indexedDb";
import { getAudiobookDisplayTitle, formatBytes } from "../utils/format";
import type { GenerationState, GeneratingItem } from "./Generation_State.vue";
import type { VoiceLogic } from "../Voices/Voice_Logic.vue";
import { pickGoogleDriveFile, preloadGoogleDrivePicker } from "../Auth/GoogleDrivePicker";

export interface GenerationArguments {
    textId: string;
    textAccessToken: string;
    filename: string;
    charCount: number;
    voice: string;
    rate: string;
    pitch: string;
}

export interface GenerationLogic {
    handleBatchFileSelect(files: FileList | File[]): Promise<void>;
    resetSelection(): void;
    submitPastedText(raw: string): Promise<void>;
    submitPastedLink(raw: string): Promise<void>;
    openTextInputSheet(): void;
    closeTextInputSheet(): void;
    submitTextInputSheet(): Promise<void>;
    openAddSourceMenu(): void;
    openAddSourceMenuForFolder(folderId: string | null): void;
    closeAddSourceSheet(): void;
    importFromGoogleDrive(): Promise<void>;
    openScanSheet(): void;
    closeScanSheet(): void;
    addScannedImage(file: File): void;
    removeScannedImage(index: number): void;
    submitScannedImages(): Promise<void>;
    scanHighQualityPdf(file: File): Promise<void>;
    cancelUpload(): void;
    onGenerateClick(): Promise<void>;
    onLoginPromptConfirm(): void;
    closeModal(): void;
    formattedSpeedLabel(value: number): string;
    formattedPitchLabel(value: number): string;
}

const BATCH_CONCURRENCY = 8;

function toAudioFilename(originalName: string): string {
    const dot = originalName.lastIndexOf(".");
    const base = dot > 0 ? originalName.substring(0, dot) : originalName;
    return `${base}.mp3`;
}

export function useGenerationLogic(state: GenerationState, voiceLogic: VoiceLogic): GenerationLogic {
    const authStore = useAuthStore();
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    function getUploadLimitBytes(): number {
        return authStore.isAdmin ? 50 * 1024 * 1024 : 10 * 1024 * 1024;
    }

    function getFormattedSpeed(value: number): string {
        return value >= 0 ? `+${value}%` : `${value}%`;
    }

    function getFormattedPitch(value: number): string {
        return value >= 0 ? `+${value}Hz` : `${value}Hz`;
    }

    function formattedSpeedLabel(value: number): string {
        if (value === 0) return "보통 (1.0x)";
        return value > 0 ? `빠름 (1.${value / 5}x)` : `느림 (0.${100 + value * 2}x)`;
    }

    function formattedPitchLabel(value: number): string {
        if (value === 0) return "기본 (0Hz)";
        return value > 0 ? `높음 (+${value}Hz)` : `낮음 (${value}Hz)`;
    }

    // 업로드/추출은 한 번에 하나만 진행되므로(대기 오버레이가 통째로 화면을
    // 막는다) 컨트롤러 하나만 돌려써도 된다 — "취소" 버튼이 이걸 abort한다.
    let currentUploadController: AbortController | null = null;

    function cancelUpload(): void {
        currentUploadController?.abort();
        // abort할 요청이 아직 없는 시점(예: 선택창 대기 중)에 눌러도 오버레이가
        // 그대로 남아있지 않도록, 로딩 상태는 항상 즉시 꺼서 버튼이 눈에 보이는
        // 반응을 남기게 한다.
        state.isDropzoneLoading.value = false;
        state.isComposerBusy.value = false;
    }

    function isAbortError(error: unknown): boolean {
        return error instanceof DOMException && error.name === "AbortError";
    }

    async function extractText(file: File) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("voice", voiceLogic.getSelectedVoice());
        formData.append("rate", getFormattedSpeed(state.speed.value));
        formData.append("pitch", getFormattedPitch(state.pitch.value));

        currentUploadController = new AbortController();
        const response = await fetch("/api/upload", {
            method: "POST",
            headers: authLogic.authHeaders(),
            body: formData,
            signal: currentUploadController.signal,
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "텍스트 추출 실패");
        }
        return response.json();
    }

    async function extractTextFromUrl(url: string) {
        currentUploadController = new AbortController();
        const response = await fetch("/api/extract-url", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "링크에서 텍스트를 가져오지 못했습니다.");
        return data;
    }

    async function extractTextFromYoutube(url: string) {
        currentUploadController = new AbortController();
        const response = await fetch("/api/extract-youtube", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "유튜브에서 자막을 가져오지 못했습니다.");
        return data;
    }

    async function extractPastedText(text: string) {
        currentUploadController = new AbortController();
        const response = await fetch("/api/paste-text", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "붙여넣은 텍스트를 처리하지 못했습니다.");
        return data;
    }

    function applyExtractedText(data: { text_id: string; text_access_token: string; filename: string; preview: string; char_count: number }): void {
        state.currentTextId.value = data.text_id;
        state.currentTextAccessToken.value = data.text_access_token;
        state.uploadedFileName.value = data.filename;

        state.previewText.value = data.preview;
        state.isPreviewVisible.value = true;
        state.charCount.value = data.char_count;
        state.isCharBadgeVisible.value = true;
        state.isGenerateDisabled.value = false;
        setTimeout(() => { state.isModalOpen.value = true; }, 50);
    }

    function resetSelection(): void {
        state.currentTextId.value = null;
        state.currentTextAccessToken.value = null;
        state.uploadedFileName.value = null;
        state.isFileDetailsVisible.value = false;
        state.previewText.value = "";
        state.isPreviewVisible.value = false;
        state.isCharBadgeVisible.value = false;
        state.charCount.value = 0;
        state.isGenerateDisabled.value = true;
    }

    async function uploadFile(file: File): Promise<void> {
        state.isDropzoneLoading.value = true;
        try {
            applyExtractedText(await extractText(file));
        } catch (error) {
            if (isAbortError(error)) {
                showToast("업로드를 취소했어요", "info");
            } else {
                reportClientError("generation", error);
                console.error(error);
                showToast((error as Error).message, "error");
            }
            resetSelection();
        } finally {
            state.isDropzoneLoading.value = false;
        }
    }

    async function handleFileSelect(file: File): Promise<void> {
        const maxUploadBytes = getUploadLimitBytes();
        if (file.size > maxUploadBytes) {
            showToast(`파일 크기가 너무 큽니다. 최대 ${maxUploadBytes / 1024 / 1024}MB까지 지원합니다.`, "error");
            return;
        }
        state.uploadedFileName.value = file.name;
        state.fileSizeLabel.value = formatBytes(file.size);
        state.isFileDetailsVisible.value = true;
        await uploadFile(file);
    }

    async function processBatchFiles(files: File[]): Promise<void> {
        const voice = voiceLogic.getSelectedVoice();
        const rate = getFormattedSpeed(state.speed.value);
        const pitch = getFormattedPitch(state.pitch.value);
        const totalFiles = files.length;
        let completed = 0;
        const queue = files.slice();

        showToast(`${totalFiles}개 파일 배치 변환 시작`, "info");
        async function worker() {
            while (queue.length > 0) {
                const file = queue.shift()!;
                try {
                    const data = await extractText(file);
                    const ok = await generateAudiobook({
                        textId: data.text_id,
                        textAccessToken: data.text_access_token,
                        filename: toAudioFilename(file.name),
                        charCount: data.char_count,
                        voice, rate, pitch,
                    });
                    if (ok) completed += 1;
                } catch (error) {
                    reportClientError("generation", error);
                    console.error(`파일 처리 실패: ${file.name}`, error);
                    showToast(`${file.name} 처리 실패`, "error");
                }
            }
        }
        const workerCount = Math.min(BATCH_CONCURRENCY, totalFiles);
        await Promise.all(Array.from({ length: workerCount }, worker));
        showToast(`배치 변환 완료: ${completed}/${totalFiles}`, "success");
    }

    async function handleBatchFileSelect(files: FileList | File[]): Promise<void> {
        const validFiles: File[] = [];
        for (const file of Array.from(files)) {
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

    // 공백 없이 도메인처럼 생겼으면 링크로 본다(프로토콜 생략 허용:
    // "youtu.be/abc"도 링크로 인식). 그 외(여러 줄이거나 공백을 포함한
    // 문장)는 전부 붙여넣은 텍스트로 취급한다.
    function looksLikeUrl(input: string): boolean {
        if (/\s/.test(input)) return false;
        return /^(https?:\/\/)?([\w-]+\.)+[a-z]{2,}(:\d+)?([/?#]\S*)?$/i.test(input);
    }

    function isYoutubeUrl(input: string): boolean {
        try {
            const host = new URL(input.startsWith("http") ? input : `https://${input}`).hostname
                .replace(/^www\.|^m\./, "").toLowerCase();
            return host === "youtu.be" || host === "youtube.com" || host === "youtube-nocookie.com";
        } catch {
            return false;
        }
    }

    async function submitPastedInput(raw: string): Promise<void> {
        const trimmed = raw.trim();
        if (!trimmed) return;

        const isLink = looksLikeUrl(trimmed);
        if (isLink && !authLogic.isLoggedIn()) {
            showToast("링크 가져오기는 로그인 후 이용할 수 있습니다.", "info");
            document.getElementById("headerLoginSlot")?.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }

        state.isComposerBusy.value = true;
        try {
            const data = !isLink
                ? await extractPastedText(trimmed)
                : isYoutubeUrl(trimmed) ? await extractTextFromYoutube(trimmed) : await extractTextFromUrl(trimmed);
            applyExtractedText(data);
            closeAddSourceSheet();
        } catch (error) {
            if (isAbortError(error)) {
                showToast("업로드를 취소했어요", "info");
            } else {
                reportClientError("generation", error);
                console.error(error);
                showToast((error as Error).message, "error");
            }
        } finally {
            state.isComposerBusy.value = false;
        }
    }

    // "텍스트 입력"/"링크 입력" 둘 다 같은 자동 판별 로직으로 처리한다 —
    // 사용자가 어느 쪽에 붙여넣든(예: 텍스트 입력에 링크를 붙여넣어도)
    // 내용을 보고 올바르게 처리된다. 메뉴는 발견 편의를 위해 나눴을 뿐이다.
    async function submitPastedText(raw: string): Promise<void> {
        await submitPastedInput(raw);
    }

    async function submitPastedLink(raw: string): Promise<void> {
        await submitPastedInput(raw);
    }

    function openTextInputSheet(): void {
        closeAddSourceSheet();
        state.textInputValue.value = "";
        state.isTextInputSheetOpen.value = true;
    }

    function closeTextInputSheet(): void {
        state.isTextInputSheetOpen.value = false;
    }

    async function submitTextInputSheet(): Promise<void> {
        const raw = state.textInputValue.value;
        closeTextInputSheet();
        await submitPastedText(raw);
    }

    function openAddSourceMenu(): void {
        // 홈 화면 드롭존에서 시작한 추가는 항상 루트에 들어가야 한다.
        state.targetFolderId.value = null;
        state.isFileSourceMenuOpen.value = true;
        preloadGoogleDrivePicker();
    }

    function openAddSourceMenuForFolder(folderId: string | null): void {
        state.targetFolderId.value = folderId;
        state.isFileSourceMenuOpen.value = true;
        preloadGoogleDrivePicker();
    }

    function closeAddSourceSheet(): void {
        state.isFileSourceMenuOpen.value = false;
    }

    async function extractDriveFile(fileId: string, accessToken: string) {
        currentUploadController = new AbortController();
        const response = await fetch("/api/import-drive-file", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ file_id: fileId, access_token: accessToken }),
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "구글 드라이브에서 파일을 가져오지 못했습니다.");
        return data;
    }

    async function importFromGoogleDrive(): Promise<void> {
        closeAddSourceSheet();
        if (!authLogic.isLoggedIn()) {
            showToast("Google Drive 가져오기는 로그인 후 이용할 수 있습니다.", "info");
            document.getElementById("headerLoginSlot")?.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }
        try {
            const config = await fetch("/api/config").then((r) => r.json());
            const clientId = config.providers?.google;
            if (!clientId) throw new Error("Google 설정이 준비되지 않았습니다.");
            // 로딩 오버레이(취소 버튼 포함)는 실제 업로드/추출 요청이 시작된
            // 뒤에만 띄운다 — 그 전에 띄우면 사용자가 아직 Google 선택창과
            // 상호작용해야 하는데 전체화면 오버레이가 가로막고, 취소를 눌러도
            // 아직 abort할 요청이 없어 아무 반응이 없는 것처럼 보였다.
            const picked = await pickGoogleDriveFile(clientId, config.google_api_key || "");
            if (!picked) return; // 사용자가 선택창을 취소함
            state.isComposerBusy.value = true;
            try {
                applyExtractedText(await extractDriveFile(picked.fileId, picked.accessToken));
            } finally {
                state.isComposerBusy.value = false;
            }
        } catch (error) {
            if (isAbortError(error)) {
                showToast("업로드를 취소했어요", "info");
            } else {
                reportClientError("generation", error);
                console.error(error);
                showToast((error as Error).message, "error");
            }
        }
    }

    async function extractScannedImages(files: File[]) {
        const formData = new FormData();
        for (const file of files) formData.append("files", file);
        currentUploadController = new AbortController();
        const response = await fetch("/api/scan-text", {
            method: "POST",
            headers: authLogic.authHeaders(),
            body: formData,
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "이미지에서 텍스트를 추출하지 못했습니다.");
        return data;
    }

    function openScanSheet(): void {
        closeAddSourceSheet();
        state.isScanSheetOpen.value = true;
    }

    function closeScanSheet(): void {
        state.isScanSheetOpen.value = false;
        state.scannedImages.value = [];
    }

    function addScannedImage(file: File): void {
        state.scannedImages.value = [...state.scannedImages.value, file];
    }

    function removeScannedImage(index: number): void {
        state.scannedImages.value = state.scannedImages.value.filter((_, i) => i !== index);
    }

    async function submitScannedImages(): Promise<void> {
        if (state.scannedImages.value.length === 0) return;
        state.isComposerBusy.value = true;
        try {
            applyExtractedText(await extractScannedImages(state.scannedImages.value));
            state.scannedImages.value = [];
            state.isScanSheetOpen.value = false;
        } catch (error) {
            if (isAbortError(error)) {
                showToast("업로드를 취소했어요", "info");
            } else {
                reportClientError("generation", error);
                console.error(error);
                showToast((error as Error).message, "error");
            }
        } finally {
            state.isComposerBusy.value = false;
        }
    }

    async function extractHighQualityPdf(file: File) {
        const formData = new FormData();
        formData.append("file", file);
        currentUploadController = new AbortController();
        const response = await fetch("/api/scan-pdf", {
            method: "POST",
            headers: authLogic.authHeaders(),
            body: formData,
            signal: currentUploadController.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "PDF에서 텍스트를 추출하지 못했습니다.");
        return data;
    }

    async function scanHighQualityPdf(file: File): Promise<void> {
        closeAddSourceSheet();
        state.isComposerBusy.value = true;
        try {
            applyExtractedText(await extractHighQualityPdf(file));
        } catch (error) {
            if (isAbortError(error)) {
                showToast("업로드를 취소했어요", "info");
            } else {
                reportClientError("generation", error);
                console.error(error);
                showToast((error as Error).message, "error");
            }
        } finally {
            state.isComposerBusy.value = false;
        }
    }

    function generationArguments(): GenerationArguments {
        return {
            textId: state.currentTextId.value!,
            textAccessToken: state.currentTextAccessToken.value!,
            filename: toAudioFilename(state.uploadedFileName.value || "unknown_doc"),
            charCount: state.charCount.value,
            voice: voiceLogic.getSelectedVoice(),
            rate: getFormattedSpeed(state.speed.value),
            pitch: getFormattedPitch(state.pitch.value),
        };
    }

    async function generateAudiobook(args: GenerationArguments): Promise<boolean> {
        const isAnonymousTrial = !authLogic.isLoggedIn();
        if (isAnonymousTrial) {
            if (!(await authLogic.canStartAnonymousTrial())) {
                state.isLoginPromptOpen.value = true;
                return false;
            }
            sessionStorage.setItem("anonymousTrialInProgress", "true");
        }

        const item: GeneratingItem = {
            id: crypto.randomUUID(),
            title: getAudiobookDisplayTitle(args.filename),
            progressPercent: 0,
            statusText: "오디오북 생성 중...",
            folderId: state.targetFolderId.value,
        };
        state.generatingItems.value.unshift(item);
        setTimeout(() => {
            document.querySelector(".library-section")?.scrollIntoView({ behavior: "smooth" });
        }, 200);

        const generationHeaders = isAnonymousTrial ? authLogic.anonymousSessionHeaders() : authLogic.authHeaders();

        function removeItem() {
            state.generatingItems.value = state.generatingItems.value.filter((i) => i.id !== item.id);
        }

        try {
            authLogic.trackProductEvent("generation_started");
            const formData = new FormData();
            formData.append("text_id", args.textId);
            formData.append("text_access_token", args.textAccessToken);
            formData.append("voice", args.voice);
            formData.append("rate", args.rate);
            formData.append("pitch", args.pitch);
            // 대용량 문서는 백그라운드 작업으로 넘어가 서버가 직접 오디오북
            // 행을 만든다(아래 entry.folderId는 그 경로를 안 탄다) — 폴더
            // 배치를 여기서도 실어 보내야 그 경로에서도 적용된다.
            if (state.targetFolderId.value) formData.append("folder_id", state.targetFolderId.value);

            const response = await fetch("/api/synthesize", {
                method: "POST",
                headers: generationHeaders,
                body: formData,
            });
            if (!response.ok) throw new Error("오디오북 변환 요청 실패. 서버 연결을 확인하세요.");

            const responseData = await response.json();
            const jobId = responseData.job_id;
            if (responseData.background_started) {
                // 이 세션 전용 목록(generatingItems)에서 빼고, 재접속해도
                // 이어 보이는 알림 기능 쪽 목록(showBackgroundJobLoading)으로
                // 넘긴다 — 완료 시 그쪽에서 지운다.
                removeItem();
                (window as any).__rememberBackgroundJob?.(jobId, args.filename, state.targetFolderId.value);
                (window as any).__showBackgroundJobLoading?.(jobId, args.filename, state.targetFolderId.value);
                showToast("서버에서 백그라운드 생성이 시작되었습니다. 완료되면 보관함에 저장됩니다.", "info");
                return true;
            }

            async function pollJobStatus(id: string): Promise<any> {
                const pollResponse = await fetch(`/api/job/${id}`, { headers: generationHeaders });
                if (!pollResponse.ok) throw new Error("작업 상태 통신 실패");
                const jobData = await pollResponse.json();
                if (jobData.status === "processing") {
                    const completedChunks = Number(jobData.completed_chunks) || 0;
                    const totalChunks = Number(jobData.total_chunks) || 0;
                    if (totalChunks > 0) {
                        item.progressPercent = Math.min(Math.round((completedChunks / totalChunks) * 100), 100);
                        item.statusText = `음성 변환 중... (${completedChunks}/${totalChunks})`;
                    } else {
                        item.statusText = "음성 변환 준비 중...";
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
            item.progressPercent = 100;
            item.statusText = "저장 중...";

            const entry = {
                id: crypto.randomUUID(),
                title: args.filename,
                audioData: await audioBlob.arrayBuffer(),
                sentences: completedJobData.sentences,
                displayMarkdown: completedJobData.display_markdown || "",
                timestamp: Date.now(),
                dateString: new Date().toLocaleDateString("ko-KR", {
                    year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit",
                }),
                sizeBytes: audioBlob.size,
                charCount: args.charCount,
                folderId: state.targetFolderId.value,
            };
            await saveAudiobookToDB(entry);
            if (isAnonymousTrial) localStorage.setItem("anonymousTrialUsed", "true");
            removeItem();
            showToast("저장되었습니다!", "success");
            authLogic.trackProductEvent("generation_completed");
            (window as any).__renderLibrary?.();
            if (authLogic.isLoggedIn()) (window as any).__syncAudiobooksToCloud?.();
            return true;
        } catch (error) {
            console.error(error);
            removeItem();
            showToast((error as Error).message, "error");
            authLogic.trackProductEvent("generation_failed");
            return false;
        } finally {
            if (isAnonymousTrial) sessionStorage.removeItem("anonymousTrialInProgress");
        }
    }

    function runPendingGeneration(): void {
        const pendingGeneration = sessionStorage.getItem("pendingGeneration");
        if (!pendingGeneration || !authLogic.isLoggedIn()) return;
        sessionStorage.removeItem("pendingGeneration");
        try {
            const args = JSON.parse(pendingGeneration);
            setTimeout(() => generateAudiobook(args), 300);
        } catch (error) {
            console.error("Failed to parse pending generation args", error);
        }
    }
    runPendingGeneration();

    function closeModal(): void {
        state.isModalOpen.value = false;
        voiceLogic.stopPreview();
    }

    async function onGenerateClick(): Promise<void> {
        if (!state.currentTextId.value) return;
        closeModal();
        try {
            await (window as any).__requestPushNotificationSubscription?.();
        } catch {
            console.warn("완료 알림 요청 실패");
        }
        await generateAudiobook(generationArguments());
    }

    function onLoginPromptConfirm(): void {
        sessionStorage.setItem("pendingGeneration", JSON.stringify(generationArguments()));
        state.isLoginPromptOpen.value = false;
        state.isModalOpen.value = false;
        const loginButton = document.getElementById("googleLoginBtn");
        loginButton?.scrollIntoView({ behavior: "smooth", block: "center" });
        (loginButton?.querySelector('div[role="button"]') as HTMLElement | null)?.click();
    }

    return {
        handleBatchFileSelect,
        resetSelection,
        submitPastedText,
        submitPastedLink,
        openTextInputSheet,
        closeTextInputSheet,
        submitTextInputSheet,
        openAddSourceMenu,
        openAddSourceMenuForFolder,
        closeAddSourceSheet,
        importFromGoogleDrive,
        openScanSheet,
        closeScanSheet,
        addScannedImage,
        removeScannedImage,
        submitScannedImages,
        scanHighQualityPdf,
        cancelUpload,
        onGenerateClick,
        onLoginPromptConfirm,
        closeModal,
        formattedSpeedLabel,
        formattedPitchLabel,
    };
}

export default {};
</script>
