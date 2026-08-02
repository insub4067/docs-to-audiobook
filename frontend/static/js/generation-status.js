(function initializeGenerationStatusModule() {
    window.TextAudio = window.TextAudio || {};

    window.TextAudio.createGenerationStatusController = function createGenerationStatusController({
        audioList,
        libraryEmpty,
    }) {
        function createItem(audioFilename) {
            const safeAudioFilename = escapeHtml(getAudiobookDisplayTitle(audioFilename));
            const item = document.createElement("div");
            item.className = "audio-item audio-item-generating";
            item.innerHTML = `
                <div class="audio-title-group">
                    <div class="generating-spinner"></div>
                    <div class="generating-info">
                        <span class="audio-title">${safeAudioFilename}</span>
                        <div class="generating-progress-track">
                            <div class="generating-progress-fill" style="width: 0%"></div>
                        </div>
                        <span class="generating-status">오디오북 생성 중...</span>
                    </div>
                </div>
            `;
            return item;
        }

        function find(jobId) {
            return Array.from(audioList.querySelectorAll(".audio-item-generating"))
                .find((item) => item.dataset.backgroundJobId === jobId) || null;
        }

        function show(jobId, title = "오디오북") {
            const existing = find(jobId);
            if (existing) return existing;

            const item = createItem(title);
            item.dataset.backgroundJobId = jobId;
            item.querySelector(".generating-status").textContent = "서버에서 생성 중...";
            audioList.prepend(item);
            libraryEmpty.style.display = "none";
            return item;
        }

        function remove(jobId) {
            find(jobId)?.remove();
            if (audioList.children.length === 0) libraryEmpty.style.display = "flex";
        }

        return { create: createItem, show, remove };
    };
})();
