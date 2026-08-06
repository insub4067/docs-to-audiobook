import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach } from "vitest";

import AudioListItemView from "../components/Library/AudioListItem_View.vue";
import type { AudiobookRecord } from "../services/indexedDb";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";

function record(overrides: Partial<AudiobookRecord> = {}): AudiobookRecord {
    return {
        id: "book-1",
        title: "데미안.pdf",
        sentences: [{ text: "문장", start: 0, end: 1000 }],
        timestamp: Date.now(),
        ...overrides,
    };
}

function mountRow(audio: AudiobookRecord) {
    return mount(AudioListItemView, { props: { audio, logic: {} as AudioListLogic } });
}

beforeEach(() => {
    setActivePinia(createPinia());
});

// 서점 카드와 같은 규칙을 서재에도 적용한다. 다만 개인 오디오북은 재생 위치와
// 총 길이를 서버가 아니라 IndexedDB에 들고 있다.
describe("서재 목록의 청취 진행률", () => {
    it("들은 적 없으면 진행률을 보여주지 않는다", () => {
        const wrapper = mountRow(record({ durationSeconds: 3600 }));

        expect(wrapper.find(".library-progress").exists()).toBe(false);
        expect(wrapper.find(".library-progress-done").exists()).toBe(false);
    });

    it("총 길이를 아직 모르면 진행률을 보여주지 않는다", () => {
        // 한 번도 열지 않은 오디오북은 리더가 길이를 저장할 기회가 없었다.
        // 0으로 나누면 Infinity가 되어 막대가 깨진다.
        const wrapper = mountRow(record({ lastPosition: 900 }));

        expect(wrapper.find(".library-progress").exists()).toBe(false);
    });

    it("듣는 중이면 퍼센트와 남은 시간을 보여준다", () => {
        const wrapper = mountRow(record({ lastPosition: 900, durationSeconds: 3600 }));

        expect(wrapper.text()).toContain("25% · 약 45분 남음");
        expect(wrapper.find(".library-progress-fill").attributes("style")).toContain("width: 25%");
    });

    it("97%를 넘으면 완료로 본다", () => {
        const wrapper = mountRow(record({ lastPosition: 3500, durationSeconds: 3600 }));

        expect(wrapper.find(".library-progress-done").text()).toBe("모두 들음");
        expect(wrapper.find(".library-progress").exists()).toBe(false);
    });

    it("이어 듣기 버튼은 두지 않는다", () => {
        // 행을 누르면 마지막 위치에서 이어지므로 버튼이 중복이다.
        const wrapper = mountRow(record({ lastPosition: 900, durationSeconds: 3600 }));

        expect(wrapper.find(".library-resume-btn").exists()).toBe(false);
    });
});
