<script lang="ts">
import type { ReaderState } from "./Reader_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls/ReaderControls_Logic.vue";
import type { RepeatMode } from "./ReaderControls/ReaderControls_State.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { useWebSpeech } from "./webSpeech";
import { buildDisplayItems, findActiveSentenceIndex, type ReaderSentence } from "./sentenceDisplay";
import { saveAudiobookToDB, updateAudiobookPosition, saveAudiobookDuration, type AudiobookRecord } from "../services/indexedDb";
import { getBookmarks, toggleBookmark, removeBookmarkAt, type BookmarkRecord } from "../services/bookmarks";
import { getAudiobookDisplayTitle, formatTime, getReaderScrollTarget } from "../utils/format";
import { useToastLogic, setReaderOpenForToast } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { swallowed } from "../services/clientErrors";

export interface SharedReaderModeOptions {
    shareId?: string | null;
    // 재생목록(뉴스 연속 재생)이 있을 때 다음 항목으로 넘길 콜백. 현재 반복
    // 모드를 함께 넘겨 "전체 반복"이면 마지막 항목 뒤에 처음으로 돌아갈지
    // 큐 쪽에서 판단하게 한다.
    onEnded?: (repeatMode: RepeatMode) => void;
    playlistKind?: "news" | null;
    // 라이브러리 작품처럼 실제 audiobooks 행이 있는 콘텐츠는 재생 위치를
    // 서버에 이어 듣기용으로 저장/복원할 수 있다 — 24시간짜리 임시 공유
    // 링크(shareId)에는 해당 없다.
    audiobookId?: string | null;
    resumeSeconds?: number;
    // 재생목록 안에서 항목만 바꿀 때는 읽기 화면을 펼치지 않는다 —
    // 미니 플레이어에서 스와이프로 넘기거나, 듣던 기사가 끝나 다음으로
    // 자동으로 넘어가는 경우다. 이미 열려 있다면 그대로 둔다.
    openReaderUI?: boolean;
}

export interface ReaderLogic {
    open(audio: AudiobookRecord, options?: { autoplay?: boolean; openReaderUI?: boolean }): void;
    restoreLastSession(audio: AudiobookRecord): void;
    openSharedReaderMode(title: string, sentences: ReaderSentence[], audioUrl: string, options?: SharedReaderModeOptions): void;
    closeReader(): void;
    reopenReader(): void;
    dismissMiniPlayer(): void;
    checkSharedLink(): Promise<void>;
    togglePlayPause(): void;
    seekTo(fraction: number): void;
    onSentenceClick(index: number): void;
    onHeadingClick(heading: { sentIndex: number; startMs: number }): void;
    currentChapterIndex(): number;
    goToChapter(offset: number): void;
    toggleBookmarkForCurrentSentence(): void;
    openBookmarkSheet(): void;
    closeBookmarkSheet(): void;
    goToBookmark(bookmark: BookmarkRecord): void;
    removeBookmark(bookmark: BookmarkRecord): void;
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
    openPlaylistSheet(): void;
    closePlaylistSheet(): void;
    closePlaylistSheetIfOpen(): boolean;
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
    let sharedAudiobookId: string | null = null;
    let lastSharedPositionSaveSecond = -1;
    const authLogic = useAuthLogic();
    let lastPositionSaveSecond = -1;
    let lastPlaybackSyncTime = 0;
    // 장 경계를 "넘어선 순간"을 잡으려면 직전 시각이 필요하다.
    let previousTimeSecond = 0;
    let lastToggleTime = 0;
    // "첫 재생" 지표(playback_started)는 콘텐츠를 열어 재생을 시작한 횟수다.
    // 일시정지 후 다시 누른 것은 새로운 시작이 아니므로, 리더를 열 때마다
    // 한 번만 찍는다.
    let playbackStartTracked = false;

    function trackPlaybackStartOnce(): void {
        if (playbackStartTracked) return;
        playbackStartTracked = true;
        authLogic.trackProductEvent("playback_started");
    }
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
            handleChapterBoundary(el, previousTimeSecond);
            previousTimeSecond = currentSec;
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
                    audioListLogic.savePlaybackState(audioObject, currentSec, settings).catch(swallowed("playback_save", "재생 상태 저장 실패:"));
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
        state.sharedPlaylistKind.value = null;
        sharedAudiobookId = null;
        state.currentAudioObject.value = audio;
        sentences = (audio.sentences || []) as ReaderSentence[];

        lastPositionSaveSecond = -1;
        playbackStartTracked = false;
        previousTimeSecond = 0;
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
            if (el.duration && !isNaN(el.duration)) {
                state.durationLabel.value = formatTime(el.duration);
                state.durationSeconds.value = el.duration;
                // 목록에서 진행률을 보여주려면 총 길이가 필요한데, 이걸 알려면
                // 오디오를 디코딩해야 한다. 어차피 여기서 알게 되므로 한 번만
                // 저장해 두고 목록은 그 값을 읽어 쓴다.
                audio.durationSeconds = audio.durationSeconds || el.duration;
                saveAudiobookDuration(audio.id, el.duration).catch(swallowed("playback_save", "재생시간 저장 실패:"));
            }
            if (audio.lastPosition && audio.lastPosition > 0) el.currentTime = audio.lastPosition;
            el.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
            if (autoplay) {
                el.play().catch((error) => console.log("Autoplay blocked:", error));
                state.isPlaying.value = true;
            }
        };
        el.onplay = () => { state.isPlaying.value = true; trackPlaybackStartOnce(); };
        el.onpause = () => { state.isPlaying.value = false; };
        // 반복 모드 처리. resetAudioHandlers()가 onended를 지우므로 매번 다시
        // 걸어야 한다 — 이걸 빠뜨려서 "전체 문서 반복"을 골라도 재생이 그냥
        // 끝나 버렸다.
        el.onended = readerControls.onEnded;
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

    // 라이브러리 작품처럼 실제 audiobooks 행이 있는 공유 모드 콘텐츠의
    // 재생 위치를 서버에 저장한다 — IndexedDB에 로컬로 들고 있는 게
    // 아니라(오디오 자체를 로컬에 받아두지 않음) 클라우드 재생 기록에만
    // 직접 쓴다.
    async function saveSharedPlaybackPosition(audiobookId: string, position: number): Promise<void> {
        if (!authLogic.isLoggedIn()) return;
        const settings = readerControls.getPlaybackSettings();
        await fetch(`/api/audiobooks/${audiobookId}/playback`, {
            method: "PUT",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
                current_time_seconds: position,
                playback_speed: settings.playbackSpeed,
                repeat_mode: settings.repeatMode,
            }),
        });
    }

    function openSharedReaderMode(title: string, sharedSentences: ReaderSentence[], audioUrl: string, options: SharedReaderModeOptions = {}): void {
        const { shareId = null, onEnded, playlistKind = null, audiobookId = null, resumeSeconds = 0, openReaderUI = true } = options;
        const el = state.audioEl.value;
        if (!el) return;
        state.sharedPlaylistKind.value = playlistKind;
        isSharedMode = true;
        sharedAudioUrl = audioUrl;
        sharedShareId = shareId;
        sharedAudiobookId = audiobookId;
        state.currentAudioObject.value = null;
        sentences = sharedSentences;
        playbackStartTracked = false;
        previousTimeSecond = 0;

        state.title.value = getAudiobookDisplayTitle(title);
        state.isPlaying.value = false;
        state.showShareBtn.value = false;
        state.showSaveSharedBtn.value = true;
        state.currentTimeLabel.value = formatTime(resumeSeconds);
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
            if (el.duration && !isNaN(el.duration)) {
                state.durationLabel.value = formatTime(el.duration);
                state.durationSeconds.value = el.duration;
            }
            if (resumeSeconds > 0) el.currentTime = resumeSeconds;
            el.playbackRate = readerControls.getPlaybackSettings().playbackSpeed;
            el.play().catch((error) => console.log("Autoplay blocked:", error));
            state.isPlaying.value = true;
        };
        el.onplay = () => { state.isPlaying.value = true; trackPlaybackStartOnce(); };
        el.onpause = () => { state.isPlaying.value = false; };
        el.ontimeupdate = () => {
            const currentSec = el.currentTime;
            const duration = el.duration || 0;
            state.currentTimeLabel.value = formatTime(currentSec);
            if (duration > 0) state.progressPercent.value = (currentSec / duration) * 100;
            handleChapterBoundary(el, previousTimeSecond);
            previousTimeSecond = currentSec;
            updateHighlight(currentSec * 1000);

            const currentSecond = Math.floor(currentSec);
            if (sharedAudiobookId && currentSecond % 30 === 0 && currentSecond > 0 && currentSecond !== lastSharedPositionSaveSecond) {
                lastSharedPositionSaveSecond = currentSecond;
                saveSharedPlaybackPosition(sharedAudiobookId, currentSec).catch(swallowed("playback_save", "재생 상태 저장 실패:"));
            }
        };
        // "현재 오디오 반복"은 지금 것만 다시 틀고 끝. "전체 반복"은 재생목록
        // 전체를 도는 뜻이므로 큐가 있으면 큐에 맡기고(마지막 항목에서 처음으로
        // 되돌아가는 건 큐 쪽이 판단한다), 큐가 없으면 그 오디오 하나가 곧
        // 전체이므로 그것만 반복한다. 반복 모드는 큐 콜백에 넘겨준다 —
        // News_Logic이 ReaderControls에 직접 접근하지 못해서다.
        el.onended = () => {
            const repeatMode = readerControls.getPlaybackSettings().repeatMode;
            if (repeatMode === "one") {
                readerControls.onEnded();
                return;
            }
            if (onEnded) {
                onEnded(repeatMode);
                return;
            }
            if (repeatMode === "all") readerControls.onEnded();
        };
        el.src = audioUrl;
        el.load();

        if (openReaderUI) {
            state.isOpen.value = true;
            setReaderOpenForToast(true);
            requestAnimationFrame(measureReaderBars);
        }
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

    /** 그 시각에 재생 중인 장의 인덱스. 없으면 -1. */
    function chapterIndexAtSecond(second: number): number {
        const headings = state.headings.value;
        for (let i = headings.length - 1; i >= 0; i--) {
            if (headings[i].startMs / 1000 <= second) return i;
        }
        return -1;
    }

    /** 장의 끝(초). 마지막 장은 오디오 끝까지다. */
    function chapterEndSecond(index: number, el: HTMLAudioElement): number {
        const next = state.headings.value[index + 1];
        return next ? next.startMs / 1000 : (el.duration || 0);
    }

    /** "현재 장 반복"과 "이 장이 끝나면 정지"를 처리한다.
     *
     * 장 판정에 activeIndex를 쓰면 안 된다 — 경계에서는 강조가 이미 다음
     * 장으로 넘어가 있어 엉뚱한 장을 반복하게 된다. 직전 시각(previousSecond)이
     * 아직 그 장 안에 있으므로 그걸로 판정하고, 경계를 "넘어선 순간"만 잡는다. */
    function handleChapterBoundary(el: HTMLAudioElement, previousSecond: number): void {
        const settings = readerControls.getPlaybackSettings();
        const repeatChapter = settings.repeatMode === "chapter";
        const stopAtEnd = readerControls.isStopAtChapterEnd();
        if (!repeatChapter && !stopAtEnd) return;

        const index = chapterIndexAtSecond(previousSecond);
        if (index < 0) return;
        const endSecond = chapterEndSecond(index, el);
        if (!endSecond) return;
        if (previousSecond >= endSecond || el.currentTime < endSecond) return;

        if (repeatChapter) {
            el.currentTime = state.headings.value[index].startMs / 1000;
            el.play().catch((error) => console.log("Play failed:", error));
            return;
        }
        el.pause();
        el.currentTime = endSecond;
        readerControls.clearStopAtChapterEnd();
        showToast("이 장이 끝나 멈췄습니다.", "info");
    }

    /** 지금 재생 중인 장의 인덱스. 아직 첫 장 전이면 -1. */
    function currentChapterIndex(): number {
        const headings = state.headings.value;
        const activeIndex = state.activeIndex.value;
        if (activeIndex < 0) return headings.length > 0 ? 0 : -1;
        // 뒤에서부터 찾는다 — 현재 문장을 지나지 않은 첫 장이 곧 현재 장이다.
        for (let i = headings.length - 1; i >= 0; i--) {
            if (headings[i].sentIndex <= activeIndex) return i;
        }
        return -1;
    }

    /** 장 단위로 건너뛴다. offset이 -1이면 이전 장, +1이면 다음 장.
     *
     * "이전 장"은 음악 앱의 이전 곡과 같게 동작한다 — 장을 재생한 지
     * 얼마 안 됐으면 진짜 이전 장으로 가고, 한참 들었으면 현재 장의
     * 처음으로 돌아간다. 그래야 한 번 눌러 장을 다시 듣기 쉽다. */
    function goToChapter(offset: number): void {
        const headings = state.headings.value;
        const el = state.audioEl.value;
        if (!el || headings.length === 0) return;

        const current = currentChapterIndex();
        let target = current + offset;
        if (offset < 0 && current >= 0) {
            const elapsed = el.currentTime - headings[current].startMs / 1000;
            if (elapsed > 3) target = current;
        }
        target = Math.max(0, Math.min(headings.length - 1, target));
        onHeadingClick(headings[target]);
    }

    /** 북마크는 개인 오디오북(IndexedDB id)과 라이브러리 작품(서버 id)을
     *  같은 스토어에 담는다. 둘 다 안정적인 id를 갖고 있어서다. */
    function currentAudiobookKey(): string | null {
        return state.currentAudioObject.value?.id || sharedAudiobookId;
    }

    function toggleBookmarkForCurrentSentence(): void {
        const audiobookId = currentAudiobookKey();
        const index = state.activeIndex.value;
        const sentence = sentences[index];
        if (!audiobookId || index < 0 || !sentence) {
            showToast("저장할 문장이 없습니다.", "info");
            return;
        }
        const saved = toggleBookmark({
            audiobookId,
            sentenceIndex: index,
            text: sentence.text,
            seconds: sentence.start / 1000,
            createdAt: Date.now(),
        });
        showToast(saved ? "문장을 저장했어요" : "문장 저장을 해제했어요", saved ? "success" : "info");
    }

    function openBookmarkSheet(): void {
        const audiobookId = currentAudiobookKey();
        state.bookmarks.value = audiobookId ? getBookmarks(audiobookId) : [];
        state.isBookmarkSheetOpen.value = true;
    }

    function closeBookmarkSheet(): void {
        state.isBookmarkSheetOpen.value = false;
    }

    function goToBookmark(bookmark: BookmarkRecord): void {
        closeBookmarkSheet();
        const el = state.audioEl.value;
        if (!el) return;
        el.currentTime = bookmark.seconds;
        el.play().catch((error) => console.log("Play failed:", error));
        state.isScrolledAway.value = false;
        requestAnimationFrame(() => scrollToSentence(bookmark.sentenceIndex));
    }

    function removeBookmark(bookmark: BookmarkRecord): void {
        removeBookmarkAt(bookmark.audiobookId, bookmark.sentenceIndex);
        state.bookmarks.value = state.bookmarks.value.filter((b) => b.sentenceIndex !== bookmark.sentenceIndex);
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

    function openPlaylistSheet(): void {
        state.isPlaylistSheetOpen.value = true;
    }

    function closePlaylistSheet(): void {
        state.isPlaylistSheetOpen.value = false;
    }

    function closePlaylistSheetIfOpen(): boolean {
        if (!state.isPlaylistSheetOpen.value) return false;
        closePlaylistSheet();
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
            audioListLogic.savePlaybackState(audioObject, el.currentTime, settings).catch(swallowed("playback_save", "재생 상태 저장 실패:"));
        } else if (el && sharedAudiobookId && el.currentTime > 0) {
            saveSharedPlaybackPosition(sharedAudiobookId, el.currentTime).catch(swallowed("playback_save", "재생 상태 저장 실패:"));
        }
        lastPositionSaveSecond = -1;
        state.isOpen.value = false;
        setReaderOpenForToast(false);
        // 목록이 들고 있는 레코드는 리더가 쓰는 것과 다른 사본이다
        // (openItem이 IndexedDB에서 새로 읽어 넘긴다). 방금 들은 만큼과
        // 이번에 알아낸 총 길이가 목록 진행률에 반영되도록 다시 읽는다.
        audioListLogic.refresh().catch((error) => console.error("목록 갱신 실패:", error));
    }

    // 미니 플레이어를 눌러 같은 재생 세션으로 되돌아간다 — open()과 달리
    // 오디오/문장/스크롤 상태를 그대로 두고 화면만 다시 펼친다.
    /** 미니 플레이어를 내린다(재생 세션 종료). 목록에서 다시 고르면
     *  마지막 위치부터 이어진다 — 내리기 전에 위치를 저장하기 때문이다. */
    function dismissMiniPlayer(): void {
        const el = state.audioEl.value;
        el?.pause();
        closeReader();
        state.title.value = "";
        state.currentAudioObject.value = null;
        state.sharedPlaylistKind.value = null;
        state.isPlaying.value = false;
        sharedAudiobookId = null;
    }

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
            setTimeout(() => openSharedReaderMode(data.title, data.sentences, data.audio_url, { shareId }), 500);
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
            openSharedReaderMode(data.title, data.sentences, data.audio_url, { shareId: match[1] });
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
    // 아직 합성 중인 문서의 앞 구간을 듣는 경로. 공유 리더 모드를 그대로
    // 쓴다 — 저장된 오디오북이 아니라 임시 URL과 문장만 있으면 되는 상황이
    // 정확히 같기 때문이다.
    (window as any).__openPartialReaderMode = (
        title: string, sentences: ReaderSentence[], audioUrl: string,
    ) => openSharedReaderMode(title, sentences, audioUrl, {});

    return {
        open, restoreLastSession, openSharedReaderMode, closeReader, reopenReader, dismissMiniPlayer, checkSharedLink,
        togglePlayPause, seekTo, onSentenceClick, onHeadingClick,
        currentChapterIndex, goToChapter,
        toggleBookmarkForCurrentSentence, openBookmarkSheet, closeBookmarkSheet,
        goToBookmark, removeBookmark,
        onReaderContentScroll, jumpToCurrentSentence,
        openIndexSheet, closeIndexSheet, closeIndexSheetIfOpen,
        openMoreSheet, closeMoreSheet, closeMoreSheetIfOpen,
        openSettingsSheet, closeSettingsSheet, closeSettingsSheetIfOpen,
        openPlaylistSheet, closePlaylistSheet, closePlaylistSheetIfOpen,
        importSharedLink, saveSharedAudiobook, attachReaderResizeHandler,
    };
}

export default {};
</script>
