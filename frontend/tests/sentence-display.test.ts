import { describe, it, expect } from "vitest";
import {
    buildDisplayItems,
    findActiveSentenceIndex,
    type ReaderSentence,
} from "../Reader/sentenceDisplay";

// 백엔드가 만들어 주는 형태: 문장마다 start/end(ms)가 있다.
function s(text: string, start: number, end: number): ReaderSentence {
    return { text, start, end };
}

// 재생 위치 → 지금 읽고 있는 문장 인덱스. 이 계산이 틀리면 하이라이트가
// 엉뚱한 문장에 붙거나 자동 스크롤이 튄다(과거 Google TTS 타이밍 드리프트
// 버그가 났던 지점).
describe("findActiveSentenceIndex", () => {
    const sentences = [s("첫째", 0, 1000), s("둘째", 1000, 2000), s("셋째", 2000, 3000)];

    it("구간 안의 시각이면 그 문장을 고른다", () => {
        expect(findActiveSentenceIndex(sentences, 500)).toBe(0);
        expect(findActiveSentenceIndex(sentences, 1500)).toBe(1);
        expect(findActiveSentenceIndex(sentences, 2500)).toBe(2);
    });

    it("첫 문장 시작 이전이면 첫 문장을 고른다", () => {
        expect(findActiveSentenceIndex(sentences, -100)).toBe(0);
    });

    it("마지막 문장이 끝난 뒤에는 마지막 문장에 머문다", () => {
        // 재생이 끝나도 하이라이트가 사라지면 안 된다.
        expect(findActiveSentenceIndex(sentences, 99999)).toBe(2);
    });

    it("문장 사이 공백 구간에서는 직전 문장을 유지한다", () => {
        // 무음 구간에서 하이라이트가 -1로 튀면 화면이 깜빡인다.
        const gapped = [s("첫째", 0, 1000), s("둘째", 5000, 6000)];
        expect(findActiveSentenceIndex(gapped, 3000)).toBe(0);
    });

    it("문장이 없으면 -1", () => {
        expect(findActiveSentenceIndex([], 0)).toBe(-1);
    });

    it("경계값(start/end와 정확히 같은 시각)을 포함한다", () => {
        expect(findActiveSentenceIndex(sentences, 0)).toBe(0);
        // end와 다음 start가 겹치면 먼저 오는 문장이 이긴다.
        expect(findActiveSentenceIndex(sentences, 1000)).toBe(0);
    });
});

describe("buildDisplayItems", () => {
    it("일반 문장은 sentence 아이템으로 만들고 마크다운 기호를 지운다", () => {
        const { items, headings } = buildDisplayItems([s("**굵게** 그리고 _기울임_", 0, 1000)], false);

        expect(headings).toEqual([]);
        expect(items).toHaveLength(1);
        expect(items[0]).toMatchObject({ kind: "sentence", index: 0 });
        expect((items[0] as { text: string }).text.trim()).toBe("굵게 그리고 기울임");
    });

    it("마크다운 #의 개수로 제목 수준을 정한다", () => {
        const { items, headings } = buildDisplayItems(
            [s("# 1장", 0, 500), s("### 소제목", 500, 900), s("본문", 900, 1500)],
            false,
        );

        expect(items.map((i) => i.kind)).toEqual(["heading", "heading", "sentence"]);
        expect(headings).toEqual([
            { text: "1장", level: 1, sentIndex: 0, startMs: 0 },
            { text: "소제목", level: 3, sentIndex: 1, startMs: 500 },
        ]);
    });

    it("type:heading + display가 있으면 그 값을 제목으로 쓴다", () => {
        const { items, headings } = buildDisplayItems(
            [{ text: "무시되는 원문", start: 0, end: 100, type: "heading", display: "표시용 제목", level: 2 }],
            false,
        );

        expect(items[0]).toMatchObject({ kind: "heading", text: "표시용 제목", level: 2 });
        expect(headings[0].text).toBe("표시용 제목");
    });

    it("#만 있고 제목 텍스트가 없으면 제목으로 보지 않는다", () => {
        const { items, headings } = buildDisplayItems([s("#", 0, 100)], false);

        expect(items[0].kind).toBe("sentence");
        expect(headings).toEqual([]);
    });

    it("supportTables=false면 표 셀도 그냥 문장으로 나열한다", () => {
        // 공유 리더 모드는 표를 그리지 않는다.
        const cells: ReaderSentence[] = [
            { text: "이름:홍길동", start: 0, end: 100, table: { id: "t1", row: 0, column: 0, header: "이름" } },
            { text: "나이:20", start: 100, end: 200, table: { id: "t1", row: 0, column: 1, header: "나이" } },
        ];
        const { items } = buildDisplayItems(cells, false);

        expect(items.map((i) => i.kind)).toEqual(["sentence", "sentence"]);
    });

    it("supportTables=true면 같은 표의 셀을 하나의 table 아이템으로 묶는다", () => {
        const cells: ReaderSentence[] = [
            { text: "이름:홍길동", start: 0, end: 100, table: { id: "t1", row: 0, column: 0, header: "이름" } },
            { text: "나이:20", start: 100, end: 200, table: { id: "t1", row: 0, column: 1, header: "나이" } },
            { text: "이름:김철수", start: 200, end: 300, table: { id: "t1", row: 1, column: 0, header: "이름" } },
            { text: "나이:31", start: 300, end: 400, table: { id: "t1", row: 1, column: 1, header: "나이" } },
            s("표 뒤의 본문", 400, 500),
        ];
        const { items } = buildDisplayItems(cells, true);

        expect(items.map((i) => i.kind)).toEqual(["table", "sentence"]);
        const table = items[0] as { columns: number; header: string[]; rows: Array<Array<{ text: string } | null>> };
        expect(table.columns).toBe(2);
        expect(table.header).toEqual(["이름", "나이"]);
        // 셀 텍스트에서 "헤더:" 접두사는 떼고 보여준다.
        expect(table.rows.map((r) => r.map((c) => c?.text))).toEqual([
            ["홍길동", "20"],
            ["김철수", "31"],
        ]);
    });

    it("표 다음에 오는 문장의 인덱스가 밀리지 않는다", () => {
        // 표 셀을 훑느라 증가시킨 인덱스를 되돌리지 않으면 표 뒤 문장의
        // index가 어긋나 하이라이트가 엉뚱한 곳에 붙는다.
        const cells: ReaderSentence[] = [
            { text: "a", start: 0, end: 100, table: { id: "t1", row: 0, column: 0, header: "h" } },
            { text: "b", start: 100, end: 200, table: { id: "t1", row: 0, column: 1, header: "h2" } },
            s("표 뒤의 본문", 200, 300),
        ];
        const { items } = buildDisplayItems(cells, true);

        expect(items[1]).toMatchObject({ kind: "sentence", index: 2 });
    });
});
