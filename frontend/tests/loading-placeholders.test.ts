import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import AudioListView from "../components/Library/AudioList_View.vue";
import ProfileView from "../Profile/Profile_View.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAuthStore } from "../stores/auth";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useThemeState } from "../Theme/Theme_State.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { MyFilesLogic } from "../Files/MyFiles_Logic.vue";
import type { AudiobookRecord } from "../services/indexedDb";

// 앱 전반의 "갑자기 튀어나오는 화면" 제거. 목록이나 카드가 늦게 나타나면
// 그 아래 내용이 통째로 밀려, 누르려던 것이 손가락 밑에서 움직인다.

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.restoreAllMocks();
});

function mountAudioList(overrides: Record<string, unknown> = {}) {
    const state = useAudioListState();
    const logic = { load: vi.fn(), refresh: vi.fn() } as unknown as AudioListLogic;
    return {
        state,
        wrapper: mount(AudioListView, {
            props: {
                state, logic,
                myFilesLogic: {} as MyFilesLogic,
                generatingItems: [],
                autoLoad: false,
                ...overrides,
            },
            global: { stubs: { AudioListItemView: true, ActionSheetView: true } },
        }),
    };
}

describe("보관함 목록 자리표시자", () => {
    it("아직 못 읽었으면 자리표시자를 보여 준다", () => {
        const { wrapper } = mountAudioList();

        expect(wrapper.findAll(".list-row-placeholder").length).toBeGreaterThan(0);
        wrapper.unmount();
    });

    it("아직 못 읽었을 때 \"책이 없습니다\"라고 하지 않는다", () => {
        // 예전에는 IndexedDB를 읽는 동안 빈 상태 문구가 잠깐 떴다가
        // 목록이 들어차며 사라졌다. 잠깐이라도 거짓말이다.
        const { wrapper } = mountAudioList();
        const empty = wrapper.find(".library-empty");

        expect((empty.element as HTMLElement).style.display).toBe("none");
        wrapper.unmount();
    });

    it("다 읽었는데 비어 있으면 그때 빈 상태를 보여 준다", async () => {
        const { state, wrapper } = mountAudioList();

        state.loaded.value = true;
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".list-row-placeholder").exists()).toBe(false);
        expect((wrapper.find(".library-empty").element as HTMLElement).style.display).not.toBe("none");
        wrapper.unmount();
    });

    it("목록을 넘겨받는 쪽(즐겨찾기 등)에는 자리표시자를 깔지 않는다", () => {
        // 이미 읽어 둔 것을 걸러서 주므로 기다릴 것이 없다.
        const { wrapper } = mountAudioList({ items: [] as AudiobookRecord[] });

        expect(wrapper.find(".list-row-placeholder").exists()).toBe(false);
        wrapper.unmount();
    });
});

describe("프로필 계정 카드 자리표시자", () => {
    function mountProfile() {
        // 목을 손으로 만들면 화면이 읽는 필드를 빠뜨려 자리표시자와 무관한
        // 이유로 깨진다. 실제 상태 팩토리를 그대로 쓴다.
        return mount(ProfileView, {
            props: {
                active: true,
                themeState: useThemeState(),
                themeLogic: { openSheet: vi.fn() },
                controlsState: useReaderControlsState(),
                controlsLogic: { openSheet: vi.fn() },
                hasMiniPlayer: false,
            } as never,
            global: { stubs: true },
        });
    }

    it("세션 확인 중에는 카드 자리를 잡아 둔다", () => {
        // 토큰은 localStorage에 바로 있으니 "로그인한 사용자"임은 즉시 안다.
        // /api/auth/me 응답을 기다리는 동안 카드가 없으면, 나중에 맨 위에
        // 끼어들며 아래 설정 카드를 밀어낸다.
        localStorage.setItem("authToken", "토큰");

        const wrapper = mountProfile();

        expect(wrapper.find(".redacted-avatar").exists()).toBe(true);
        wrapper.unmount();
    });

    it("비로그인이면 자리를 잡지 않는다", () => {
        const wrapper = mountProfile();

        expect(wrapper.find(".redacted-avatar").exists()).toBe(false);
        wrapper.unmount();
    });

    it("세션이 확인되면 자리표시자를 치우고 계정을 보여 준다", async () => {
        localStorage.setItem("authToken", "토큰");
        const wrapper = mountProfile();

        useAuthStore().setSession({ id: "u", email: "a@a.com", is_admin: false }, "토큰");
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".redacted-avatar").exists()).toBe(false);
        expect(wrapper.text()).toContain("a@a.com");
        wrapper.unmount();
    });
});
