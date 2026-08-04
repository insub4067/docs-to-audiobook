<script lang="ts">
import type { ReaderState } from "./Reader_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { useWebSpeech } from "./webSpeech";
import { buildDisplayItems, findActiveSentenceIndex, type ReaderSentence } from "./sentenceDisplay";
import { saveAudiobookToDB, updateAudiobookPosition, type AudiobookRecord } from "../services/indexedDb";
import { getAudiobookDisplayTitle, formatTime, getReaderScrollTarget } from "../utils/format";
import { useToastLogic, setReaderOpenForToast } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";

export interface ReaderLogic {
    open(audio: AudiobookRecord): void;
    restoreLastSession(audio: AudiobookRecord): void;
    openSharedReaderMode(title: string, sentences: ReaderSentence[], audioUrl: string, shareId?: string | null, onEnded?: () => void): void;
    closeReader(): void;
    reopenReader(): void;
    checkSharedLink(): Promise<void>;
    togglePlayPause(): void;
    seekTo(fraction: number): void;
    onSentenceClick(index: number): void;
    onHeadingClick(heading: { sentIndex: number; startMs: number }): void;
    onReaderContentScroll(): void;
    jumpToCurrentSentence(): void;
    openIndexSheet(): void;
    closeIndexSheet(): void;
    closeIndexSheetIfOpen(): boolean;
    openMoreSheet(): void;
    closeMoreSheet(): void;
    closeMoreSheetIfOpen(): boolean;
    openSettingsSheet(): void;
    closeSettingsSheet(): void;
    closeSettingsSheetIfOpen(): boolean;
    importSharedLink(url: string): Promise<void>;
    saveSharedAudiobook(): Promise<void>;
    attachReaderResizeHandler(): () => void;
}

// static/js/reader.js를 옮긴 것.
export function useReaderLogic(state: ReaderState, readerControls: ReaderControlsLogic, audioListLogic: AudioListLogic): ReaderLogic {
    const { showToast } = useToastLogic(useToastState());
    const webSpeech = useWebSpeech(showToast);

    let sentences: ReaderSentence[] = [];
    let currentObjectUrl: string | null = null;
    let isSharedMode = false;
    let sharedAudioUrl: string | null = null;
    let sharedShareId: string | null = null;
    let lastPositionSaveSecond = -1;
    let lastPlaybackSyncTime = 0;
    let lastToggleTime = 0;
    // 우리가 직접 부른 scrollTo(smooth)가 끝나기 전에 scroll 이벤트가
    // 튀어서 "사용자가 스크롤해서 벗어났다"로 오인하지 않도록 잠깐 무시한다.
    let suppressScrollAwayUntil = 0;

    function measureReaderBars(): void {
        const container = state.containerEl.value;
        if (!container) return;
        const header = container.querySelector<HTMLElement>(".reader-header");
        const controls = container.querySelector<HTMLElement>(".reader-controls");
        if (header) container.style.setProperty("--reader-header-h", header.offsetHeight + "px");
        if (controls) container.style.setProperty("--reader-controls-h", controls.offsetHeight + "px");
    }

    function resetAudioHandlers(): void {
        const el = state.audioEl.value;
        if (!el) return;
        el.onplay = null;
        el.onpause = null;
        el.ontimeupdate = null;
        el.onloadedmetadata = null;
        el.onerror = null;
        el.onended = null;
    }

    function isElementInView(container: HTMLElement, element: HTMLElement): boolean {
        const containerRect = container.getBoundingClientRect();
        const elementRect = element.getBoundingClientRect();
        return elementRect.bottom > containerRect.top && elementRect.top < containerRect.bottom;
    }

    function scrollToSentence(index: number): void {
        const content = state.contentEl.value;
        if (!content) return;
        const activeSpan = document.getElementById(`sent-${index}`);
        if (!activeSpan) return;
        suppressScrollAwayUntil = Date.now() + 500;
        content.scrollTo({ top: getReaderScrollTarget(content, activeSpan), behavior: "smooth" });
    }

    function updateHighlight(currentMs: number): void {
        const activeIndex = findActiveSentenceIndex(sentences, currentMs);
        if (activeIndex !== state.activeIndex.value) {
            state.activeIndex.value = activeIndex;
            // 사용자가 위로 스크롤해 다른 부분을 읽고 있으면(isScrolledAway),
            // 문장이 넘어갈 때마다 강제로 도로 끌고 오지 않는다 — "현재
            // 위치로" 버튼으로 본인이 원할 때 돌아오게 한다.
            if (!state.isScrolledAway.value) {
                requestAnimationFrame(() => scrollToSentence(activeIndex));
            }
        }
    }

    // .reader-content의 @scroll에 연결한다. 활성 문장이 보이는 영역을
    // 벗어나면 "현재 위치로" 버튼을 띄운다.
    function onReaderContentScroll(): void {
        if (Date.now() < suppressScrollAwayUntil) return;
        const content = state.contentEl.value;
        if (!content || state.activeIndex.value < 0) return;
        const activeSpan = document.getElementById(`sent-${state.activeIndex.value}`);
        if (!activeSpan) return;
        state.isScrolledAway.value = !isElementInView(content, activeSpan);
    }

    function jumpToCurrentSentence(): void {
        if (state.activeIndex.value >= 0) scrollToSentence(state.activeIndex.value);
        state.isScrolledAway.value = false;
    }

    function bindLocalTimeUpdate(): void {
        const el = state.audioEl.value;
        if (!el) return;
        el.ontimeupdate = () => {
            const currentSec = el.currentTime;
            const currentMs = currentSec * 1000;
            const duration = el.duration || 0;
            state.currentTimeLabel.value = formatTime(currentSec);
            if (duration > 0) state.progressPercent.value = (currentSec / duration) * 100;
            updateHighlight(currentMs);

            const currentSecond = Math.floor(currentSec);
            const audioObject = state.currentAudioObject.value;
            if (audioObject && currentSecond % 5 === 0 && currentSecond > 0 && currentSecond !== lastPositionSaveSecond) {
                lastPositionSaveSecond = currentSecond;
                const settings = readerControls.getPlaybackSettings();
                audioObject.playbackSpeed = settings.playbackSpeed;
                audioObject.repeatMode = settings.repeatMode;
                updateAudiobookPosition(audioObject.id, currentSec);
                if (Date.now() - lastPlaybackSyncTime >= 30000) {
                    lastPlaybackSyncTime = Date.now();
                    audioListLogic.savePlaybackState(audioObject, currentSec, settings).catch((error) => console.error("재생 상태 저장 실패:", error));
                }
            }
        };
    }

    // openReaderUI=false + autoplay=false는 PWA를 새로 열었을 때 마지막 세션을
    // 미니 플레이어에 표시만 하기 위한 용도(restoreLastSession)다 — 리더 화면을
    // 펼치지 않고 재생도 하지 않은 채로 오디오/문장/제목 상태만 채워 넣는다.
    function open(audio: AudiobookRecord, options: { autoplay?: boolean; openReaderUI?: boolean } = {}): void {
        const { autoplay = true, openReaderUI = true } = options;
        if (currentObjectUrl) {
            URL.revokeObjectURL(currentObjectUrl);
            currentObjectUrl = null;
        }
        const el = state.audioEl.value;
        if (!el) return;
        const audioBlob = audio.audioData instanceof Blob ? audio.audioData : new Blob([audio.audioData as ArrayBuffer], { type: "audio/mpeg" });
        const localUrl = URL.createObjectURL(audioBlob);
        currentObjectUrl = localUrl;
        isSharedMode = false;
        state.currentAudioObject.value = audio;
        sentences = (audio.sentences || []) as ReaderSentence[];

        lastPositionSaveSecond = -1;
        readerControls.applyPlaybackSettings({ playbackSpeed: audio.playbackSpeed, repeatMode: audio.repeatMode });
        state.title.value = getAudiobookDisplayTitle(audio.title);
        state.isPlaying.value = false;
        state.showShareBtn.value = true;
        state.showSaveSharedBtn.value = false;
        state.currentTimeLabel.value = formatTime(audio.lastPosition || 0);
        state.durationLabel.value = "00:00";
        state.progressPercent.value = 0;
        state.activeIndex.value = -1;

        const { items, headings } = buildDisplayItems(sentences, true);
        state.displayItems.value = items;
        state.headings.value = headings;

        resetAudioHandlers();
        el.onerror = () => {
            console.error("Audio load error:", el.error?.code ?? "unknown");
            showToast(`오디오 로드 실패 (code: ${el.error?.code ?? "?"})`, "error");
        };
        el.onloadedmetadata = () => {
            if (el.duration && !isNaN(el.duration)) state.durationLabel.value = formatTime(el.duration);
            if (audio.lastPosition && audio.lastPosition > 0) el.currentTime = audio.lastPosition;
            el.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
            if (autoplay) {
                el.play().catch((error) => console.log("Autoplay blocked:", error));
                state.isPlaying.value = true;
            }
        };
        el.onplay = () => { state.isPlaying.value = true; };
        el.onpause = () => { state.isPlaying.value = false; };
        bindLocalTimeUpdate();
        el.src = localUrl;
        el.load();
        if (autoplay) el.play().catch(() => {});

        if (openReaderUI) {
            state.isOpen.value = true;
            setReaderOpenForToast(true);
            requestAnimationFrame(measureReaderBars);
        }
    }

    function restoreLastSession(audio: AudiobookRecord): void {
        open(audio, { autoplay: false, openReaderUI: false });
    }

    function openSharedReaderMode(title: string, sharedSentences: ReaderSentence[], audioUrl: string, shareId: string | null = null, onEnded?: () => void): void {
        const el = state.audioEl.value;
        if (!el) return;
        isSharedMode = true;
        sharedAudioUrl = audioUrl;
        sharedShareId = shareId;
        state.currentAudioObject.value = null;
        sentences = sharedSentences;

        state.title.value = getAudiobookDisplayTitle(title);
        state.isPlaying.value = false;
        state.showShareBtn.value = false;
        state.showSaveSharedBtn.value = true;
        state.currentTimeLabel.value = "00:00";
        state.durationLabel.value = "00:00";
        state.progressPercent.value = 0;
        state.activeIndex.value = -1;

        const { items, headings } = buildDisplayItems(sharedSentences, false);
        state.displayItems.value = items;
        state.headings.value = headings;

        resetAudioHandlers();
        el.onerror = () => {
            console.error("Shared audio load error:", el.error?.code ?? "unknown");
            showToast("공유 오디오를 불러올 수 없습니다.", "error");
        };
        el.onloadedmetadata = () => {
            if (el.duration && !isNaN(el.duration)) state.durationLabel.value = formatTime(el.duration);
            el.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
            el.play().catch((error) => console.log("Autoplay blocked:", error));
            state.isPlaying.value = true;
        };
        el.onplay = () => { state.isPlaying.value = true; };
        el.onpause = () => { state.isPlaying.value = false; };
        el.ontimeupdate = () => {
            const currentSec = el.currentTime;
            const duration = el.duration || 0;
            state.currentTimeLabel.value = formatTime(currentSec);
            if (duration > 0) state.progressPercent.value = (currentSec / duration) * 100;
            updateHighlight(currentSec * 1000);
        };
        el.onended = onEnded || null;
        el.src = audioUrl;
        el.load();

        state.isOpen.value = true;
        setReaderOpenForToast(true);
        requestAnimationFrame(measureReaderBars);
    }

    function togglePlayPause(): void {
        const el = state.audioEl.value;
        if (!el) return;
        const now = Date.now();
        if (now - lastToggleTime < 300) return;
        lastToggleTime = now;
        if (el.paused) {
            el.play().catch((error) => {
                console.log("Play failed:", error);
                if (isSharedMode) {
                    const textContent = state.contentEl.value?.innerText || "";
                    if (textContent.trim() && window.speechSynthesis) {
                        showToast("오디오 재생 실패. Web Speech API로 읽을까요?", "info");
                        setTimeout(() => {
                            if (window.confirm("Web Speech API로 텍스트를 읽으시겠습니까?\n(오디오북을 생성할 수 없는 경우의 대체 방법입니다)")) {
                                webSpeech.speak(textContent, "ko-KR", el.playbackRate || 1.0, 1.0);
                                state.isPlaying.value = true;
                            }
                        }, 100);
                    }
                }
            });
        } else {
            el.pause();
            if (isSharedMode) webSpeech.stop();
        }
    }

    function seekTo(fraction: number): void {
        const el = state.audioEl.value;
        if (el && el.duration) el.currentTime = fraction * el.duration;
    }

    function onSentenceClick(index: number): void {
        const el = state.audioEl.value;
        const sentence = sentences[index];
        if (!el || !sentence) return;
        el.currentTime = sentence.start / 1000;
        el.play().catch((error) => console.log("Play failed:", error));
        state.isScrolledAway.value = false;
    }

    function onHeadingClick(heading: { sentIndex: number; startMs: number }): void {
        closeIndexSheet();
        const el = state.audioEl.value;
        if (!el) return;
        el.currentTime = heading.startMs / 1000;
        el.play().catch((error) => console.log("Play failed:", error));
        state.isScrolledAway.value = false;
        requestAnimationFrame(() => scrollToSentence(heading.sentIndex));
    }

    function openIndexSheet(): void {
        state.isIndexSheetOpen.value = true;
    }

    function closeIndexSheet(): void {
        state.isIndexSheetOpen.value = false;
    }

    function closeIndexSheetIfOpen(): boolean {
        if (!state.isIndexSheetOpen.value) return false;
        closeIndexSheet();
        return true;
    }

    function openMoreSheet(): void {
        state.isMoreSheetOpen.value = true;
    }

    function closeMoreSheet(): void {
        state.isMoreSheetOpen.value = false;
    }

    function closeMoreSheetIfOpen(): boolean {
        if (!state.isMoreSheetOpen.value) return false;
        closeMoreSheet();
        return true;
    }

    function openSettingsSheet(): void {
        state.isSettingsSheetOpen.value = true;
    }

    function closeSettingsSheet(): void {
        state.isSettingsSheetOpen.value = false;
    }

    function closeSettingsSheetIfOpen(): boolean {
        if (!state.isSettingsSheetOpen.value) return false;
        closeSettingsSheet();
        return true;
    }

    // "닫기"는 재생 세션을 끝내지 않는다 — 화면만 접고(미니 플레이어로),
    // 재생 중이면 계속 재생, 일시정지면 그대로 유지한다. 그래서 오디오
    // 핸들러(ontimeupdate 등)도 그대로 두어야 미니 플레이어가 실시간으로
    // 갱신된다. 다른 오디오북을 열면 open()이 알아서 처음부터 다시
    // 초기화하므로 여기서 따로 정리할 필요가 없다.
    function closeReader(): void {
        const el = state.audioEl.value;
        const audioObject = state.currentAudioObject.value;
        if (el && audioObject && el.currentTime > 0) {
            updateAudiobookPosition(audioObject.id, el.currentTime);
            audioObject.lastPosition = el.currentTime;
            const settings = readerControls.getPlaybackSettings();
            audioObject.playbackSpeed = settings.playbackSpeed;
            audioObject.repeatMode = settings.repeatMode;
            audioListLogic.savePlaybackState(audioObject, el.currentTime, settings).catch((error) => console.error("재생 상태 저장 실패:", error));
        }
        lastPositionSaveSecond = -1;
        state.isOpen.value = false;
        setReaderOpenForToast(false);
    }

    // 미니 플레이어를 눌러 같은 재생 세션으로 되돌아간다 — open()과 달리
    // 오디오/문장/스크롤 상태를 그대로 두고 화면만 다시 펼친다.
    function reopenReader(): void {
        state.isOpen.value = true;
        setReaderOpenForToast(true);
        requestAnimationFrame(measureReaderBars);
    }

    // 헤더/컨트롤 높이가 바뀔 수 있는 뷰포트 리사이즈(회전, 가상 키보드 등)에서
    // --reader-header-h/--reader-controls-h를 다시 잰다. View의 onMounted에서
    // 한 번 호출하고, 반환값을 onUnmounted에서 호출해 리스너를 정리한다.
    function attachReaderResizeHandler(): () => void {
        function onResize(): void {
            if (state.isOpen.value) measureReaderBars();
        }

        window.addEventListener("resize", onResize);

        return () => {
            window.removeEventListener("resize", onResize);
        };
    }

    async function checkSharedLink(): Promise<void> {
        const match = window.location.pathname.match(/^\/share\/([a-zA-Z0-9-]+)$/);
        if (!match) return;
        const shareId = match[1];
        try {
            showToast("공유된 오디오북을 불러오는 중...", "info");
            const response = await fetch(`/api/share/${shareId}`);
            if (!response.ok) {
                showToast(response.status === 404 ? "공유 링크가 만료되었거나 존재하지 않습니다." : "오디오북을 불러올 수 없습니다.", "error");
                return;
            }
            const data = await response.json();
            setTimeout(() => openSharedReaderMode(data.title, data.sentences, data.audio_url, shareId), 500);
        } catch (error) {
            console.error("Failed to load shared audiobook:", error);
            showToast("공유 오디오북 로드에 실패했습니다.", "error");
        }
    }

    async function importSharedLink(url: string): Promise<void> {
        const match = url.match(/\/share\/([a-zA-Z0-9-]+)/);
        if (!match) {
            showToast("유효한 공유 링크가 아닙니다.", "error");
            return;
        }
        try {
            showToast("공유 링크 정보를 불러오는 중...", "info");
            const response = await fetch(`/api/share/${match[1]}`);
            if (!response.ok) throw new Error("공유 링크가 만료되었거나 존재하지 않습니다.");
            const data = await response.json();
            openSharedReaderMode(data.title, data.sentences, data.audio_url, match[1]);
        } catch (error) {
            console.error(error);
            showToast((error as Error).message || "공유 링크 불러오기에 실패했습니다.", "error");
        }
    }

    async function saveSharedAudiobook(): Promise<void> {
        if (!sharedAudioUrl) return;
        try {
            showToast("저장 중...", "info");
            const response = await fetch(sharedAudioUrl);
            if (!response.ok) throw new Error("Audio fetch failed");
            const audioBlob = await response.blob();
            await saveAudiobookToDB({
                id: Date.now().toString(), title: state.title.value, audioData: audioBlob,
                sentences: sentences as unknown[], shareId: sharedShareId || undefined,
                shareExpiry: Date.now() + (23 * 60 * 60 * 1000),
            });
            await audioListLogic.refresh();
            state.showSaveSharedBtn.value = false;
            showToast("저장되었습니다!", "success");
        } catch (error) {
            console.error("Save shared audiobook error:", error);
            showToast("저장 실패했습니다.", "error");
        }
    }

    (window as any).__openReaderMode = open;

    return {
        open, restoreLastSession, openSharedReaderMode, closeReader, reopenReader, checkSharedLink,
        togglePlayPause, seekTo, onSentenceClick, onHeadingClick,
        onReaderContentScroll, jumpToCurrentSentence,
        openIndexSheet, closeIndexSheet, closeIndexSheetIfOpen,
        openMoreSheet, closeMoreSheet, closeMoreSheetIfOpen,
        openSettingsSheet, closeSettingsSheet, closeSettingsSheetIfOpen,
        importSharedLink, saveSharedAudiobook, attachReaderResizeHandler,
    };
}

export default {};
</script>
