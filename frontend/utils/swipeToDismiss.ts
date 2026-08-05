import { onMounted, onUnmounted, type Ref } from "vue";

// static/app.js의 setupSwipeToDismiss를 그대로 옮긴 것. 바텀시트류
// (생성 모달, 액션시트, 로그인 안내) 전부에서 재사용하므로 UI 상태 없는
// 순수 유틸로 둔다(View/State/Logic 3분할 예외).
//
// handleElement: 터치를 감지할 영역이 실제로 움직이는(transform이 걸리는)
// contentElement와 다를 때만 넘긴다(예: 읽기 화면은 상단바를 끌어야 화면
// 전체가 따라 내려간다). 생략하면 기존 방식대로 contentElement 자신이
// 손잡이 역할도 겸한다.
export function useSwipeToDismiss(
    contentElement: Ref<HTMLElement | null>,
    onDismiss: () => void,
    handleElement?: Ref<HTMLElement | null>,
): void {
    let startY = 0;
    let currentY = 0;
    let isDragging = false;
    let dragStartTime = 0;

    function onTouchStart(event: TouchEvent) {
        const el = contentElement.value;
        if (!el) return;
        const scrollable = (event.target as HTMLElement).closest(".modal-scroll-area, .index-sheet-list, .news-list-scroll");
        if (scrollable && scrollable.scrollTop > 0) return;
        startY = event.touches[0].clientY;
        currentY = startY;
        isDragging = true;
        dragStartTime = Date.now();
        el.classList.add("ui-dragging");
        el.style.transition = "none";
    }

    function onTouchMove(event: TouchEvent) {
        const el = contentElement.value;
        if (!isDragging || !el) return;
        const scrollable = (event.target as HTMLElement).closest(".modal-scroll-area, .index-sheet-list, .news-list-scroll");
        const currentYPosition = event.touches[0].clientY;
        const deltaY = currentYPosition - startY;
        if (scrollable && (scrollable.scrollTop > 0 || deltaY < 0)) {
            isDragging = false;
            el.classList.remove("ui-dragging");
            el.style.transform = "";
            el.style.transition = "";
            return;
        }
        currentY = currentYPosition;
        if (deltaY > 0) {
            el.style.transform = `translateY(${deltaY}px)`;
            if (event.cancelable && !scrollable) event.preventDefault();
        } else {
            el.style.transform = `translateY(${deltaY * 0.2}px)`;
        }
    }

    function onTouchEnd() {
        const el = contentElement.value;
        if (!isDragging || !el) return;
        isDragging = false;
        el.classList.remove("ui-dragging");
        el.style.transition = "";
        const deltaY = currentY - startY;
        const velocity = deltaY / (Date.now() - dragStartTime);
        if (deltaY > 0 && (deltaY > el.offsetHeight * 0.25 || (velocity > 0.6 && deltaY > 30))) {
            el.style.transform = "";
            onDismiss();
        } else {
            el.style.transform = "";
        }
    }

    function onTouchCancel() {
        const el = contentElement.value;
        if (!isDragging || !el) return;
        isDragging = false;
        el.classList.remove("ui-dragging");
        el.style.transition = "";
        el.style.transform = "";
    }

    onMounted(() => {
        const el = (handleElement ?? contentElement).value;
        if (!el) return;
        el.addEventListener("touchstart", onTouchStart, { passive: true });
        el.addEventListener("touchmove", onTouchMove, { passive: false });
        el.addEventListener("touchend", onTouchEnd, { passive: true });
        el.addEventListener("touchcancel", onTouchCancel, { passive: true });
    });

    onUnmounted(() => {
        const el = (handleElement ?? contentElement).value;
        if (!el) return;
        el.removeEventListener("touchstart", onTouchStart);
        el.removeEventListener("touchmove", onTouchMove);
        el.removeEventListener("touchend", onTouchEnd);
        el.removeEventListener("touchcancel", onTouchCancel);
    });
}
