(function initializeVoicesModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createVoiceController = function createVoiceController({
        voiceSelect,
        voiceDesc,
        voicePreviewBtn,
        voicePreviewLabel,
        fetch,
        createOption,
        createAudio,
        createObjectURL,
        notify,
        logError,
    }) {
        let availableVoices = [];
        let previewAudio = null;

        function stopPreview() {
            if (previewAudio) {
                previewAudio.pause();
                previewAudio = null;
            }
            if (voicePreviewBtn) {
                voicePreviewBtn.disabled = false;
                if (voicePreviewLabel) voicePreviewLabel.textContent = "미리듣기";
            }
        }

        function updateDescription(shortName) {
            const voice = availableVoices.find((item) => item.short_name === shortName);
            if (voice) {
                voiceDesc.textContent = voice.description || "선택한 음성의 상세 특징이 표시됩니다.";
                voiceDesc.style.opacity = 1;
            } else {
                voiceDesc.textContent = "선택한 음성의 상세 특징이 표시됩니다.";
            }
        }

        async function togglePreview() {
            if (previewAudio) {
                stopPreview();
                return;
            }
            const voice = voiceSelect.value;
            if (!voice) return;

            voicePreviewBtn.disabled = true;
            if (voicePreviewLabel) voicePreviewLabel.textContent = "준비 중...";
            try {
                const response = await fetch(`/api/voices/${encodeURIComponent(voice)}/preview`);
                if (!response.ok) throw new Error("미리듣기를 불러오지 못했습니다.");
                const blob = await response.blob();

                previewAudio = createAudio(createObjectURL(blob));
                previewAudio.onended = stopPreview;
                previewAudio.onerror = () => {
                    stopPreview();
                    notify("미리듣기를 재생하지 못했습니다.", "error");
                };
                voicePreviewBtn.disabled = false;
                if (voicePreviewLabel) voicePreviewLabel.textContent = "정지";
                await previewAudio.play();
            } catch (error) {
                logError(error);
                stopPreview();
                notify(error.message || "미리듣기에 실패했습니다.", "error");
            }
        }

        function initialize() {
            voiceSelect.addEventListener("change", (event) => {
                updateDescription(event.target.value);
                stopPreview();
            });
            voicePreviewBtn?.addEventListener("click", togglePreview);
        }

        async function loadVoices() {
            try {
                const response = await fetch("/api/voices");
                if (!response.ok) throw new Error("목소리 목록을 불러오지 못했습니다.");
                const voices = await response.json();
                availableVoices = voices;
                voiceSelect.innerHTML = "";

                if (voices.length === 0) {
                    voiceSelect.innerHTML = '<option value="ko-KR-SunHiNeural">선희 (차분한 뉴스/정보 전달 - 여성)</option>';
                    return;
                }

                voices.forEach((voice) => {
                    const option = createOption();
                    option.value = voice.short_name;
                    const flag = voice.locale.startsWith("ko-KR") ? "🇰🇷" : "🇺🇸";
                    option.textContent = `${flag} ${voice.friendly_name}`;
                    voiceSelect.appendChild(option);
                });
                voiceSelect.selectedIndex = 0;
                updateDescription(voiceSelect.value);
            } catch (error) {
                logError(error);
                notify("음성 목록을 가져오지 못했습니다. 기본 설정을 사용합니다.", "error");
                availableVoices = [
                    { short_name: "ko-KR-SunHiNeural", friendly_name: "선희 (차분한 뉴스/정보 전달 - 여성)", locale: "ko-KR", description: "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다." },
                    { short_name: "ko-KR-InJoonNeural", friendly_name: "인준 (신뢰감 있는 소설/다큐 - 남성)", locale: "ko-KR", description: "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다." },
                    { short_name: "ko-KR-JiMinNeural", friendly_name: "지민 (밝고 상냥한 동화/안내 - 여성)", locale: "ko-KR", description: "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다." },
                ];
                voiceSelect.innerHTML = `
                    <option value="ko-KR-SunHiNeural" selected>🇰🇷 선희 (차분한 뉴스/정보 전달 - 여성)</option>
                    <option value="ko-KR-InJoonNeural">🇰🇷 인준 (신뢰감 있는 소설/다큐 - 남성)</option>
                    <option value="ko-KR-JiMinNeural">🇰🇷 지민 (밝고 상냥한 동화/안내 - 여성)</option>
                `;
                updateDescription(voiceSelect.value);
            }
        }

        return {
            initialize,
            loadVoices,
            stopPreview,
            getSelectedVoice: () => voiceSelect.value,
        };
    };
})();
