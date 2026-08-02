<script lang="ts">
import { useAuthStore } from "../../stores/auth";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";
import { saveAudiobookToDB } from "../../services/indexedDb";
import { getAudiobookDisplayTitle, formatBytes } from "../../utils/format";
import type { GenerationState, GeneratingItem } from "./Generation_State.vue";
import type { VoiceLogic } from "../Voices/Voice_Logic.vue";

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
    fetchTextFromUrl(): Promise<void>;
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

    async function extractText(file: File) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("voice", voiceLogic.getSelectedVoice());
        formData.append("rate", getFormattedSpeed(state.speed.value));
        formData.append("pitch", getFormattedPitch(state.pitch.value));

        const response = await fetch("/api/upload", {
            method: "POST",
            headers: authLogic.authHeaders(),
            body: formData,
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "텍스트 추출 실패");
        }
        return response.json();
    }

    async function extractTextFromUrl(url: string) {
        const response = await fetch("/api/extract-url", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "링크에서 텍스트를 가져오지 못했습니다.");
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
            console.error(error);
            showToast((error as Error).message, "error");
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

    async function fetchTextFromUrl(): Promise<void> {
        const url = state.urlInputValue.value.trim();
        if (!url) return;
        if (!authLogic.isLoggedIn()) {
            showToast("링크 가져오기는 로그인 후 이용할 수 있습니다.", "info");
            document.getElementById("headerLoginSlot")?.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }
        state.isUrlFetchBusy.value = true;
        try {
            applyExtractedText(await extractTextFromUrl(url));
            state.urlInputValue.value = "";
        } catch (error) {
            console.error(error);
            showToast((error as Error).message, "error");
        } finally {
            state.isUrlFetchBusy.value = false;
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
                (window as any).__rememberBackgroundJob?.(jobId, args.filename);
                (window as any).__showBackgroundJobLoading?.(jobId, args.filename);
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
        } catch (error) {
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
        fetchTextFromUrl,
        onGenerateClick,
        onLoginPromptConfirm,
        closeModal,
        formattedSpeedLabel,
        formattedPitchLabel,
    };
}

export default {};
</script>
