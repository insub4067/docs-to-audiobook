import { ref } from "vue";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach } from "vitest";

import ProfileView from "../Profile/Profile_View.vue";
import { useThemeState } from "../Theme/Theme_State.vue";
import { useThemeLogic } from "../Theme/Theme_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";

function mountProfile(active: boolean) {
    const themeState = useThemeState();
    const controlsState = useReaderControlsState();
    return mount(ProfileView, {
        attachTo: document.body,
        props: {
            active,
            themeState,
            themeLogic: useThemeLogic(themeState),
            controlsState,
            controlsLogic: useReaderControlsLogic(controlsState, ref(null)),
        },
    });
}

beforeEach(() => {
    setActivePinia(createPinia());
});

// 회귀: Profile_View는 템플릿 루트가 여러 개(main + 로그아웃 확인 시트)라
// 부모가 사용처 태그에 v-show를 걸어도 Vue가 어느 루트에 적용할지 정할 수
// 없어 조용히 무시한다. 그래서 프로필 내용이 홈/서재/서점 탭 하단에 항상
// 같이 보였다. 지금은 active prop을 받아 컴포넌트 안에서 자기 루트에
// v-show를 직접 건다.
describe("Profile_View의 표시 여부", () => {
    it("active=false면 프로필 본문이 숨겨진다", () => {
        const wrapper = mountProfile(false);
        const root = wrapper.find(".profile-root").element as HTMLElement;
        expect(root.style.display).toBe("none");
        wrapper.unmount();
    });

    it("active=true면 프로필 본문이 보인다", () => {
        const wrapper = mountProfile(true);
        const root = wrapper.find(".profile-root").element as HTMLElement;
        expect(root.style.display).not.toBe("none");
        wrapper.unmount();
    });
});

// 회귀: lucide.createIcons()는 <i data-lucide="...">를 새로 만든 <svg>로
// 통째로 교체한다 — Vue의 vnode가 들고 있던 노드는 그 순간 DOM에서 떨어져
// parentNode가 null이 된다. 그 상태에서 v-if/v-else로 아이콘을 스왑하면
// Vue가 null.insertBefore(...)를 호출해 런타임 크래시가 났고, "읽기 설정"
// 아코디언이 아예 열리지 않았다. 아래 테스트는 lucide의 교체 동작을 그대로
// 흉내낸 뒤 토글해서 같은 크래시가 재발하는지 확인한다.
function replaceLucidePlaceholders(root: HTMLElement): number {
    const placeholders = Array.from(root.querySelectorAll("i[data-lucide]"));
    for (const el of placeholders) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", `lucide lucide-${el.getAttribute("data-lucide")}`);
        el.parentNode?.replaceChild(svg, el);
    }
    return placeholders.length;
}

describe("읽기 설정 아코디언", () => {
    it("lucide가 아이콘을 <svg>로 교체한 뒤에도 반복 토글에서 크래시하지 않는다", async () => {
        const wrapper = mountProfile(true);

        const replaced = replaceLucidePlaceholders(wrapper.element as HTMLElement);
        expect(replaced).toBeGreaterThan(0);

        const toggle = wrapper.find(".profile-settings-toggle");
        for (let i = 0; i < 4; i++) {
            await toggle.trigger("click");
        }

        expect(wrapper.find(".profile-settings-collapse").exists()).toBe(true);
        wrapper.unmount();
    });

    it("펼침 상태에 따라 chevron 두 개가 v-show로 교차 표시된다", async () => {
        const wrapper = mountProfile(true);
        const chevrons = wrapper.findAll(".profile-settings-toggle-chevron");
        expect(chevrons).toHaveLength(2);

        const visible = () =>
            chevrons.filter((c) => (c.element as HTMLElement).style.display !== "none").length;

        // 접힘/펼침 어느 쪽이든 보이는 chevron은 항상 정확히 하나여야 한다.
        expect(visible()).toBe(1);
        await wrapper.find(".profile-settings-toggle").trigger("click");
        expect(visible()).toBe(1);

        wrapper.unmount();
    });

    it("chevron은 v-if가 아니라 v-show로 토글해 두 개 다 DOM에 남아 있다", async () => {
        const wrapper = mountProfile(true);
        const count = () => wrapper.findAll(".profile-settings-toggle-chevron").length;

        // v-if/v-else로 되돌아가면 한 번에 한쪽만 렌더돼 개수가 1이 되고,
        // 그게 곧 lucide의 DOM 교체와 충돌하는 그 패턴이다.
        expect(count()).toBe(2);
        await wrapper.find(".profile-settings-toggle").trigger("click");
        expect(count()).toBe(2);

        wrapper.unmount();
    });
});
