document.addEventListener("DOMContentLoaded", async () => {
    lucide.createIcons();
    await initializeAuth();

    const elements = {
        voiceSelect: document.getElementById("voiceSelect"),
        voiceDesc: document.getElementById("voiceDesc"),
        voicePreviewBtn: document.getElementById("voicePreviewBtn"),
        voicePreviewLabel: document.getElementById("voicePreviewLabel"),
        libraryEmpty: document.getElementById("libraryEmpty"),
        audioList: document.getElementById("audioList"),
    };
    const generationModal = document.getElementById("generationModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const modalFocusOrigins = new WeakMap();
    const state = { objectUrls: {} };
    const services = {};

    function rememberModalFocus(backdropElement, focusElement) {
        modalFocusOrigins.set(backdropElement, document.activeElement);
        requestAnimationFrame(() => focusElement?.focus());
    }

    function restoreModalFocus(backdropElement) {
        const focusOrigin = modalFocusOrigins.get(backdropElement);
        if (focusOrigin instanceof HTMLElement && document.contains(focusOrigin)) focusOrigin.focus();
    }

    function openGenerationModal() {
        generationModal.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(generationModal, closeModalBtn);
    }

    function closeGenerationModal() {
        generationModal.classList.remove("show");
        document.body.style.overflow = "";
        services.voice.stopPreview();
        restoreModalFocus(generationModal);
    }

    function setupSwipeToDismiss(backdropElement, contentElementSelector) {
        if (!backdropElement) return;
        const contentElement = backdropElement.matches(contentElementSelector)
            ? backdropElement
            : backdropElement.querySelector(contentElementSelector);
        if (!contentElement) return;

        let startY = 0;
        let currentY = 0;
        let isDragging = false;
        let dragStartTime = 0;

        contentElement.addEventListener("touchstart", event => {
            const scrollable = event.target.closest(".modal-scroll-area, .index-sheet-list");
            if (scrollable && scrollable.scrollTop > 0) return;
            startY = event.touches[0].clientY;
            currentY = startY;
            isDragging = true;
            dragStartTime = Date.now();
            contentElement.classList.add("ui-dragging");
            contentElement.style.transition = "none";
        }, { passive: true });
        contentElement.addEventListener("touchmove", event => {
            if (!isDragging) return;
            const scrollable = event.target.closest(".modal-scroll-area, .index-sheet-list");
            const currentYPosition = event.touches[0].clientY;
            const deltaY = currentYPosition - startY;
            if (scrollable && (scrollable.scrollTop > 0 || deltaY < 0)) {
                isDragging = false;
                contentElement.classList.remove("ui-dragging");
                contentElement.style.transform = "";
                contentElement.style.transition = "";
                return;
            }
            currentY = currentYPosition;
            if (deltaY > 0) {
                contentElement.style.transform = `translateY(${deltaY}px)`;
                if (event.cancelable && !scrollable) event.preventDefault();
            } else contentElement.style.transform = `translateY(${deltaY * 0.2}px)`;
        }, { passive: false });
        contentElement.addEventListener("touchend", () => {
            if (!isDragging) return;
            isDragging = false;
            contentElement.classList.remove("ui-dragging");
            contentElement.style.transition = "";
            const deltaY = currentY - startY;
            const velocity = deltaY / (Date.now() - dragStartTime);
            if (deltaY > 0 && (deltaY > contentElement.offsetHeight * 0.25 || (velocity > 0.6 && deltaY > 30))) {
                contentElement.style.transform = "";
                backdropElement.classList.remove("show");
                document.body.style.overflow = "";
            } else contentElement.style.transform = "";
        }, { passive: true });
        contentElement.addEventListener("touchcancel", () => {
            if (!isDragging) return;
            isDragging = false;
            contentElement.classList.remove("ui-dragging");
            contentElement.style.transition = "";
            contentElement.style.transform = "";
        }, { passive: true });
        new MutationObserver(() => {
            if (backdropElement.classList.contains("show")) {
                contentElement.style.transform = "";
                contentElement.style.transition = "";
            }
        }).observe(backdropElement, { attributes: true, attributeFilter: ["class"] });
    }

    setupSwipeToDismiss(generationModal, ".modal-content");
    setupSwipeToDismiss(document.getElementById("actionSheetBackdrop"), ".action-sheet");
    setupSwipeToDismiss(document.getElementById("loginPromptBackdrop"), ".action-sheet");
    closeModalBtn.addEventListener("click", closeGenerationModal);

    const loginPromptBackdrop = document.getElementById("loginPromptBackdrop");
    const loginPromptConfirmBtn = document.getElementById("loginPromptConfirmBtn");
    const loginPromptCancelBtn = document.getElementById("loginPromptCancelBtn");
    function openLoginPromptSheet() {
        loginPromptBackdrop.classList.add("show");
        document.body.style.overflow = "hidden";
        rememberModalFocus(loginPromptBackdrop, loginPromptConfirmBtn);
    }
    function closeLoginPromptSheet() {
        loginPromptBackdrop.classList.remove("show");
        document.body.style.overflow = "";
        restoreModalFocus(loginPromptBackdrop);
    }
    loginPromptCancelBtn.addEventListener("click", closeLoginPromptSheet);
    loginPromptBackdrop.addEventListener("click", event => {
        if (event.target === loginPromptBackdrop) closeLoginPromptSheet();
    });

    services.voice = TextAudio.createVoiceController({
        voiceSelect: elements.voiceSelect,
        voiceDesc: elements.voiceDesc,
        voicePreviewBtn: elements.voicePreviewBtn,
        voicePreviewLabel: elements.voicePreviewLabel,
        fetch: window.fetch.bind(window),
        createOption: () => document.createElement("option"),
        createAudio: url => new Audio(url),
        createObjectURL: blob => URL.createObjectURL(blob),
        notify: showToast,
        logError: error => console.error(error),
    });
    services.generationStatus = TextAudio.createGenerationStatusController(elements);
    window.__showBackgroundJobLoading = services.generationStatus.show;
    window.__removeBackgroundJobLoading = services.generationStatus.remove;

    const appContext = { elements, state, services, setupSwipeToDismiss, rememberModalFocus, restoreModalFocus };
    services.reader = TextAudio.createReaderController(appContext);
    services.library = TextAudio.createLibraryController({
        audioList: elements.audioList,
        libraryEmpty: elements.libraryEmpty,
        readerControls: { getPlaybackSettings: () => services.reader.getPlaybackSettings() },
        openReaderMode: audio => services.reader.open(audio),
        getCurrentAudio: () => services.reader.getCurrentAudio(),
        rememberModalFocus,
        restoreModalFocus,
        objectUrls: state.objectUrls,
    });
    services.generation = TextAudio.createGenerationController({
        voiceController: services.voice,
        generationStatus: services.generationStatus,
        openGenerationModal,
        closeGenerationModal,
        openLoginPromptSheet,
        closeLoginPromptSheet,
        renderLibrary: services.library.render,
        syncWithCloud: services.library.sync,
    });

    services.voice.initialize();
    services.reader.initialize();
    services.library.initialize();
    services.generation.initialize();

    document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        if (loginPromptBackdrop.classList.contains("show")) closeLoginPromptSheet();
        else if (services.library.closeActionSheetIfOpen()) {
        } else if (services.reader.closeIndexSheetIfOpen()) {
        } else if (generationModal.classList.contains("show")) closeGenerationModal();
    });

    initDB().then(() => {
        services.voice.loadVoices();
        services.library.load();
    });
    services.reader.checkSharedLink();
    initializeBackgroundNotifications();
    initIosPwaPrompt();
});
