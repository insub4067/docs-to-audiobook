// Node 22+ 는 localStorage를 네이티브 전역으로 갖고 있는데 --localstorage-file
// 없이 실행하면 undefined를 돌려주고, 이게 jsdom이 깔아둔 것을 가려버린다
// (sessionStorage는 안 가려져서 정상). 테마/재생 설정 로직이 마운트 시점에
// 바로 localStorage를 읽으므로 최소 구현을 깔아준다 — 저장 동작 자체는 이
// 테스트의 관심사가 아니다.
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
