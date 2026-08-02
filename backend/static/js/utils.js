function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function getAudiobookDisplayTitle(title) {
    return String(title).replace(/\.[^/.]+$/, "");
}

function syncUrlClearButton(input, button) {
    button.hidden = input.value.length === 0;
}

function getReaderScrollTarget(container, activeElement) {
    const containerRect = container.getBoundingClientRect();
    const activeRect = activeElement.getBoundingClientRect();
    return container.scrollTop + activeRect.top - containerRect.top
        - container.clientHeight / 2 + activeElement.clientHeight / 2;
}

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

// Time Formatter (seconds to MM:SS)
function formatTime(seconds) {
    if (isNaN(seconds) || seconds === Infinity) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
