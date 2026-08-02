export function formatBytes(bytes: number, decimals = 2): string {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

export function getAudiobookDisplayTitle(title: string): string {
    return String(title).replace(/\.[^/.]+$/, "");
}

export function formatTime(seconds: number): string {
    if (isNaN(seconds) || seconds === Infinity) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function getReaderScrollTarget(container: HTMLElement, activeElement: HTMLElement): number {
    const containerRect = container.getBoundingClientRect();
    const activeRect = activeElement.getBoundingClientRect();
    return container.scrollTop + activeRect.top - containerRect.top
        - container.clientHeight / 2 + activeElement.clientHeight / 2;
}
