// jsdom은 IndexedDB를 구현하지 않는다. 서재 데이터가 전부 여기 저장되므로
// (기본 제공 오디오북 재시딩 등) 실제 IndexedDB와 동작하는 순수 JS 구현으로
// 채워준다.
import "fake-indexeddb/auto";

// Node 22+ 는 localStorage를 네이티브 전역으로 갖고 있는데 --localstorage-file
// 없이 실행하면 undefined를 돌려주고, 이게 jsdom이 깔아둔 것을 가려버린다
// (sessionStorage는 안 가려져서 정상). 테마/재생 설정 로직이 마운트 시점에
// 바로 localStorage를 읽으므로 최소 구현을 깔아준다 — 저장 동작 자체는 이
// 테스트의 관심사가 아니다.
// jsdom은 Blob → object URL 변환을 구현하지 않는다. 리더가 로컬 오디오를
// 재생할 때 쓰므로 형태만 맞는 최소 구현을 깔아준다.
if (!URL.createObjectURL) {
    let counter = 0;
    URL.createObjectURL = () => `blob:jsdom/${++counter}`;
    URL.revokeObjectURL = () => {};
}

if (!window.localStorage) {
    const store = new Map<string, string>();
    const shim: Storage = {
        get length() {
            return store.size;
        },
        key: (i) => Array.from(store.keys())[i] ?? null,
        getItem: (k) => (store.has(k) ? store.get(k)! : null),
        setItem: (k, v) => void store.set(k, String(v)),
        removeItem: (k) => void store.delete(k),
        clear: () => store.clear(),
    };
    Object.defineProperty(window, "localStorage", { value: shim, configurable: true });
    Object.defineProperty(globalThis, "localStorage", { value: shim, configurable: true });
}

// jsdom에는 포인터 캡처 API가 없다. 진행 바 드래그가 이걸 부르는데, 없으면
// 이벤트 핸들러가 통째로 터져 테스트 결과가 가려진다.
if (!HTMLElement.prototype.setPointerCapture) {
    HTMLElement.prototype.setPointerCapture = () => {};
    HTMLElement.prototype.releasePointerCapture = () => {};
    HTMLElement.prototype.hasPointerCapture = () => false;
}
