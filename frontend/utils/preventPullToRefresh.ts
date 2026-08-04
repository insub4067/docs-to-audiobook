// body/html의 overscroll-behavior만으로는 iOS Safari/PWA에서 풀투리프레시
// (당겨서 새로고침) 제스처가 확실히 막히지 않는다 — 문서가 맨 위이고 그
// 지점에서 더 아래로 당기는 손짓만 선택적으로 막아, 페이지가 밀려 내려가
// 상단 safe-area가 깨져 보이는 것(재실행 스냅샷처럼 보이는 현상)을 막는다.
export function preventPullToRefresh(): void {
    let startY = 0;
    let scrollableAncestor: HTMLElement | null = null;

    function findScrollableAncestor(node: HTMLElement | null): HTMLElement | null {
        let el = node;
        while (el && el !== document.body) {
            const style = getComputedStyle(el);
            if ((style.overflowY === "auto" || style.overflowY === "scroll") && el.scrollHeight > el.clientHeight) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    document.addEventListener("touchstart", (event) => {
        startY = event.touches[0].clientY;
        scrollableAncestor = findScrollableAncestor(event.target as HTMLElement);
        // eslint-disable-next-line no-console
        console.log("[PTR] touchstart", {
            startY,
            target: (event.target as HTMLElement)?.className,
            scrollableAncestor: scrollableAncestor?.className ?? null,
        });
    }, { passive: true });

    document.addEventListener("touchmove", (event) => {
        const currentY = event.touches[0].clientY;
        const pullingDown = currentY > startY;
        const scrollY = window.scrollY || document.documentElement.scrollTop;
        const documentAtTop = scrollY <= 0;
        const blockedByAncestor = !!(scrollableAncestor && scrollableAncestor.scrollTop > 0);
        const willPrevent = pullingDown && documentAtTop && !blockedByAncestor;
        // eslint-disable-next-line no-console
        console.log("[PTR] touchmove", {
            currentY, startY, pullingDown, scrollY, documentAtTop,
            scrollableAncestor: scrollableAncestor?.className ?? null,
            ancestorScrollTop: scrollableAncestor?.scrollTop ?? null,
            blockedByAncestor, willPrevent, cancelable: event.cancelable,
        });
        if (!willPrevent) return;
        event.preventDefault();
        // eslint-disable-next-line no-console
        console.log("[PTR] preventDefault called, defaultPrevented =", event.defaultPrevented);
    }, { passive: false });
}
