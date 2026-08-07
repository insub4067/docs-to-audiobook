import { mount } from "@vue/test-utils";
import { ref } from "vue";
import { describe, it, expect, beforeEach, vi } from "vitest";

import OnboardingView from "../components/Onboarding/Onboarding_View.vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { AudiobookRecord } from "../services/indexedDb";

function book(id: string, isDefault = false): AudiobookRecord {
    return { id, title: id, timestamp: 0, isDefault } as AudiobookRecord;
}

let logic: AudioListLogic;

function setup(saved: AudiobookRecord[]) {
    const state = { savedAudiobooks: ref(saved) } as unknown as AudioListState;
    return mount(OnboardingView, { props: { state, logic } });
}

/** lucide가 하는 일 그대로 — <i data-lucide>를 <svg>로 갈아치운다. */
function replaceLucidePlaceholders(root: HTMLElement): number {
    const placeholders = Array.from(root.querySelectorAll("i[data-lucide]"));
    for (const el of placeholders) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", `lucide lucide-${el.getAttribute("data-lucide")}`);
        el.parentNode?.replaceChild(svg, el);
    }
    return placeholders.length;
}

beforeEach(() => {
    localStorage.clear();
    logic = { openItem: vi.fn().mockResolvedValue(undefined) } as unknown as AudioListLogic;
});

describe("첫 방문 안내 카드", () => {
    it("자기 오디오북이 없으면 보여준다", () => {
        const wrapper = setup([book("default", true)]);

        expect(wrapper.find(".onboarding-card").exists()).toBe(true);
        expect(wrapper.text()).toContain("듣는 책으로");
    });

    it("자기 오디오북을 하나라도 만들었으면 사라진다", () => {
        // 안내는 할 일을 다 했다. 계속 남아 있으면 화면만 가린다.
        const wrapper = setup([book("default", true), book("내 문서")]);

        expect(wrapper.find(".onboarding-card").exists()).toBe(false);
    });

    it("닫으면 다시 뜨지 않는다", async () => {
        const wrapper = setup([book("default", true)]);

        await wrapper.find(".onboarding-dismiss").trigger("click");

        expect(wrapper.find(".onboarding-card").exists()).toBe(false);
        // 새로고침해도 유지돼야 하므로 localStorage에 남는다.
        expect(setup([book("default", true)]).find(".onboarding-card").exists()).toBe(false);
    });

    it("샘플 버튼을 누르면 기본 제공 오디오북을 연다", async () => {
        const sample = book("default", true);
        const wrapper = setup([sample]);

        await wrapper.find(".onboarding-sample").trigger("click");

        expect(logic.openItem).toHaveBeenCalledWith(sample);
    });

    it("기본 제공 오디오북이 아직 없으면 샘플 버튼을 숨긴다", () => {
        // 콜드스타트 직후에는 서버가 아직 합성 중이라 없을 수 있다.
        // 누르면 아무 일도 안 일어나는 버튼을 보여주느니 감춘다.
        const wrapper = setup([]);

        expect(wrapper.find(".onboarding-card").exists()).toBe(true);
        expect(wrapper.find(".onboarding-sample").exists()).toBe(false);
    });

    it("lucide가 아이콘을 <svg>로 바꾼 뒤 닫아도 크래시하지 않는다", async () => {
        // Profile 화면에서 실제로 터졌던 조합이다. lucide가 <i>를 <svg>로
        // 교체하면 Vue의 vnode는 사라진 <i>를 가리키게 되고, 그 상태로
        // v-if를 꺼서 언마운트하면 런타임이 죽었다.
        const wrapper = setup([book("default", true)]);
        const replaced = replaceLucidePlaceholders(wrapper.element as HTMLElement);
        expect(replaced).toBeGreaterThan(0);

        await wrapper.find(".onboarding-dismiss").trigger("click");

        expect(wrapper.find(".onboarding-card").exists()).toBe(false);
        wrapper.unmount();
    });
});
