(function initializeReaderControlsModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createReaderControls = function createReaderControls({
        readerAudio,
        skipBackBtn,
        skipForwardBtn,
        repeatBtn,
        repeatText,
        speedBtn,
        speedText,
        timerBtn,
        timerText,
        storage,
        notify,
        setInterval,
        clearInterval,
    }) {
        const repeatModes = ["off", "all", "one"];
        const repeatModeLabels = {
            off: "반복 안 함",
            all: "전체 반복",
            one: "한 곡 반복",
        };
        const speedOptions = [0.75, 1.0, 1.25, 1.5, 2.0];
        const timerOptions = [0, 15, 30, 60];
        let currentRepeatMode = 0;
        let currentSpeedIndex = 1;
        let currentTimerIndex = 0;
        let sleepTimerInterval = null;
        let sleepTimeRemaining = 0;

        function applyRepeatUI() {
            const mode = repeatModes[currentRepeatMode];
            repeatText.textContent = repeatModeLabels[mode];
            repeatBtn.classList.toggle("active", mode !== "off");
        }

        function applySpeedUI() {
            const speed = speedOptions[currentSpeedIndex];
            speedText.textContent = speed.toFixed(2).replace(/\.00$/, ".0") + "x";
            speedBtn.classList.toggle("active", speed !== 1.0);
        }

        function getPlaybackSettings() {
            return {
                playbackSpeed: speedOptions[currentSpeedIndex],
                repeatMode: repeatModes[currentRepeatMode],
            };
        }

        function applyPlaybackSettings({ playbackSpeed, repeatMode } = {}) {
            const speedIndex = speedOptions.indexOf(Number(playbackSpeed));
            if (speedIndex !== -1) currentSpeedIndex = speedIndex;
            const repeatIndex = repeatModes.indexOf(repeatMode);
            if (repeatIndex !== -1) currentRepeatMode = repeatIndex;
            readerAudio.playbackRate = speedOptions[currentSpeedIndex];
            applySpeedUI();
            applyRepeatUI();
        }

        function clearSleepTimer() {
            clearInterval(sleepTimerInterval);
            sleepTimerInterval = null;
            timerBtn.classList.remove("active");
            timerText.textContent = "타이머";
            currentTimerIndex = 0;
        }

        function updateTimerDisplay() {
            if (sleepTimeRemaining <= 0) return;
            const minutes = Math.floor(sleepTimeRemaining / 60);
            const seconds = sleepTimeRemaining % 60;
            timerText.textContent = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
        }

        function initialize() {
            const savedRepeatMode = storage.getItem("textAudio_repeatMode");
            const savedRepeatIndex = repeatModes.indexOf(savedRepeatMode);
            if (savedRepeatIndex !== -1) currentRepeatMode = savedRepeatIndex;

            const savedSpeed = Number.parseFloat(storage.getItem("textAudio_playbackSpeed"));
            const savedSpeedIndex = speedOptions.indexOf(savedSpeed);
            if (savedSpeedIndex !== -1) currentSpeedIndex = savedSpeedIndex;

            applyPlaybackSettings(getPlaybackSettings());

            skipBackBtn.addEventListener("click", () => {
                if (!Number.isNaN(readerAudio.currentTime)) {
                    readerAudio.currentTime = Math.max(0, readerAudio.currentTime - 10);
                }
            });
            skipForwardBtn.addEventListener("click", () => {
                if (!Number.isNaN(readerAudio.duration)) {
                    readerAudio.currentTime = Math.min(readerAudio.duration, readerAudio.currentTime + 10);
                }
            });
            repeatBtn.addEventListener("click", () => {
                currentRepeatMode = (currentRepeatMode + 1) % repeatModes.length;
                const repeatMode = repeatModes[currentRepeatMode];
                applyRepeatUI();
                storage.setItem("textAudio_repeatMode", repeatMode);
                notify(`반복 모드: ${repeatModeLabels[repeatMode]}`, "info");
            });
            readerAudio.addEventListener("ended", () => {
                const repeatMode = repeatModes[currentRepeatMode];
                if (repeatMode === "all" || repeatMode === "one") {
                    readerAudio.currentTime = 0;
                    readerAudio.play().catch((error) => console.log("Autoplay blocked:", error));
                }
            });
            speedBtn.addEventListener("click", () => {
                currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
                const playbackSpeed = speedOptions[currentSpeedIndex];
                readerAudio.playbackRate = playbackSpeed;
                applySpeedUI();
                storage.setItem("textAudio_playbackSpeed", playbackSpeed);
                notify(`재생 속도 ${playbackSpeed}x`, "info");
            });
            timerBtn.addEventListener("click", () => {
                currentTimerIndex = (currentTimerIndex + 1) % timerOptions.length;
                const minutes = timerOptions[currentTimerIndex];
                clearInterval(sleepTimerInterval);

                if (minutes === 0) {
                    clearSleepTimer();
                    notify("취침 타이머가 해제되었습니다.", "info");
                    return;
                }

                timerBtn.classList.add("active");
                sleepTimeRemaining = minutes * 60;
                updateTimerDisplay();
                sleepTimerInterval = setInterval(() => {
                    sleepTimeRemaining -= 1;
                    if (sleepTimeRemaining <= 0) {
                        readerAudio.pause();
                        clearSleepTimer();
                        notify("타이머가 종료되어 재생을 멈췄습니다.", "info");
                    } else {
                        updateTimerDisplay();
                    }
                }, 1000);
                notify(`${minutes}분 뒤에 재생이 자동 종료됩니다.`, "info");
            });
        }

        return {
            initialize,
            getPlaybackSettings,
            applyPlaybackSettings,
            clearSleepTimer,
        };
    };
})();
