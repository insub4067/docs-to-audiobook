import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useFolderBrowserState } from "../Files/FolderBrowser_State.vue";
import { useFolderBrowserLogic } from "../Files/FolderBrowser_Logic.vue";

// 폴더는 /api/folders(네트워크)에서 오고 파일은 IndexedDB에서 온다. 파일이
// 훨씬 빨리 떠서, 폴더가 나중에 목록 위로 끼어들며 아래를 통째로 밀어냈다.
// 누르려던 항목이 손가락 밑에서 움직이는 상태였다.
//
// 지난번 개수를 기억해 두면 불러오는 동안 정확히 그만큼 자리를 잡아 둘 수
// 있어, 앱을 새로 켠 직후에도 밀리지 않는다.

function setup() {
    // 호출마다 새 상태를 만드는 팩토리다(내 파일과 폴더 이동 시트가 각자
    // 독립된 탐색 스택을 가져야 해서). 그래서 테스트 간 격리가 자동이다.
    const state = useFolderBrowserState("서재");
    return { state, logic: useFolderBrowserLogic(state) };
}

function mockFolders(folders: { id: string; name: string }[]) {
    vi.stubGlobal("fetch", vi.fn(async () => ({
        ok: true,
        json: async () => ({ folders }),
    })));
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    localStorage.setItem("authToken", "토큰");
    vi.restoreAllMocks();
});

describe("서재 폴더 개수 기억", () => {
    it("처음에는 아는 개수가 없다", () => {
        const { logic } = setup();

        expect(logic.lastKnownFolderCount()).toBe(0);
    });

    it("한 번 불러오면 개수를 기억한다", async () => {
        const { logic } = setup();
        mockFolders([{ id: "a", name: "공부" }, { id: "b", name: "보고서" }, { id: "c", name: "소설" }]);

        await logic.loadCurrentFolder();

        expect(logic.lastKnownFolderCount()).toBe(3);
    });

    it("폴더마다 따로 기억한다", async () => {
        // 루트에 4개, 하위 폴더에 1개면 자리도 각각 달라야 한다.
        const { state, logic } = setup();
        mockFolders([{ id: "a", name: "공부" }, { id: "b", name: "보고서" }]);
        await logic.loadCurrentFolder();

        state.currentFolderId.value = "a";
        mockFolders([{ id: "a1", name: "하위" }]);
        await logic.loadCurrentFolder();

        expect(logic.lastKnownFolderCount()).toBe(1);
        state.currentFolderId.value = null;
        expect(logic.lastKnownFolderCount()).toBe(2);
    });

    it("폴더가 없어지면 0으로 갱신한다", async () => {
        const { logic } = setup();
        mockFolders([{ id: "a", name: "공부" }]);
        await logic.loadCurrentFolder();
        mockFolders([]);

        await logic.loadCurrentFolder();

        expect(logic.lastKnownFolderCount()).toBe(0);
    });

    it("터무니없이 큰 값이 들어 있어도 화면을 채우지 않는다", () => {
        // localStorage는 사용자가 손댈 수 있다. 자리표시자로 화면이 통째로
        // 덮이는 것보다는 조금 밀리는 편이 낫다.
        const { logic } = setup();
        localStorage.setItem("textAudio_folderCount:root", "9999");

        expect(logic.lastKnownFolderCount()).toBe(12);
    });

    it("깨진 값이 들어 있어도 0으로 다룬다", () => {
        const { logic } = setup();
        localStorage.setItem("textAudio_folderCount:root", "아무거나");

        expect(logic.lastKnownFolderCount()).toBe(0);
    });

    it("비로그인이면 불러오지 않으므로 기억도 건드리지 않는다", async () => {
        const { logic } = setup();
        mockFolders([{ id: "a", name: "공부" }]);
        await logic.loadCurrentFolder();
        localStorage.removeItem("authToken");
        mockFolders([]);

        await logic.loadCurrentFolder();

        expect(logic.lastKnownFolderCount()).toBe(1);
    });
});
