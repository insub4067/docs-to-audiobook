const toast = document.getElementById("toast");
const toastIcon = document.getElementById("toastIcon");
const toastMessage = document.getElementById("toastMessage");
const readerOverlay = document.getElementById("readerOverlay");

// Toast Notification System
let toastTimeout = null;
function showToast(message, type = "info") {
    clearTimeout(toastTimeout);
    toastMessage.textContent = message;
    toast.className = "toast";
    toast.classList.add(`toast-${type}`);

    // Reader 모드가 열려있으면 상단에서 토스트 표시
    if (readerOverlay.classList.contains("show")) {
        toast.classList.add("toast-top");
    }

    let iconName = "info";
    if (type === "success") iconName = "check-circle";
    if (type === "error") iconName = "alert-triangle";

    toastIcon.setAttribute("data-lucide", iconName);
    lucide.createIcons();

    toast.classList.add("show");

    toastTimeout = setTimeout(() => {
        toast.classList.remove("show");
    }, 3500);
}
