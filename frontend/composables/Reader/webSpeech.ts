// static/js/web-speech.js 그대로. 오디오 재생이 실패했을 때(공유 리더
// 모드) 브라우저 내장 TTS로 대체 재생하는 용도라 UI 상태가 없다.
export interface WebSpeechController {
    speak(text: string, voice?: string, rate?: number, pitch?: number): void;
    stop(): void;
}

export function useWebSpeech(notify: (message: string, type?: "info" | "success" | "error") => void): WebSpeechController {
    let currentUtterance: SpeechSynthesisUtterance | null = null;

    function speak(text: string, voice = "ko-KR", rate = 1.0, pitch = 1.0): void {
        if (!window.speechSynthesis) {
            notify("Web Speech API를 지원하지 않는 브라우저입니다.", "error");
            return;
        }
        window.speechSynthesis.cancel();
        currentUtterance = new SpeechSynthesisUtterance(text);
        currentUtterance.lang = voice;
        currentUtterance.rate = rate;
        currentUtterance.pitch = pitch;
        currentUtterance.volume = 1.0;
        currentUtterance.onstart = () => notify("🎤 Web Speech API로 읽는 중...", "info");
        currentUtterance.onend = () => { currentUtterance = null; };
        currentUtterance.onerror = (event) => notify(`Web Speech 오류: ${event.error}`, "error");
        window.speechSynthesis.speak(currentUtterance);
    }

    function stop(): void {
        if (!window.speechSynthesis) return;
        window.speechSynthesis.cancel();
        currentUtterance = null;
    }

    return { speak, stop };
}
