(function initializeWebSpeechModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createWebSpeechController = function createWebSpeechController({
        speechSynthesis,
        createUtterance,
        notify,
    }) {
        let currentUtterance = null;

        function speak(text, voice = "ko-KR", rate = 1.0, pitch = 1.0) {
            if (!speechSynthesis) {
                notify("Web Speech API를 지원하지 않는 브라우저입니다.", "error");
                return;
            }

            speechSynthesis.cancel();
            currentUtterance = createUtterance(text);
            currentUtterance.lang = voice;
            currentUtterance.rate = rate;
            currentUtterance.pitch = pitch;
            currentUtterance.volume = 1.0;
            currentUtterance.onstart = () => {
                notify("🎤 Web Speech API로 읽는 중...", "info");
            };
            currentUtterance.onend = () => {
                currentUtterance = null;
            };
            currentUtterance.onerror = (event) => {
                notify(`Web Speech 오류: ${event.error}`, "error");
            };
            speechSynthesis.speak(currentUtterance);
        }

        function stop() {
            if (!speechSynthesis) return;
            speechSynthesis.cancel();
            currentUtterance = null;
        }

        return { speak, stop };
    };
})();
