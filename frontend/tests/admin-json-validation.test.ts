// 관리자 등록 폼의 JSON 사전 검사.
//
// 이 검사기가 백엔드보다 엄격하면, 백엔드가 받아 주는 형식을 화면이
// 거절한다. 실제로 서점 시리즈(parts)를 붙여넣었을 때 "content 필드가
// 없습니다"가 떠서 등록 자체를 못 했다 — 백엔드는 이미 받고 있었는데
// 화면만 몰랐다.
import { describe, it, expect } from "vitest";

import { useAdminState } from "../Admin/Admin_State.vue";
import { useAdminLogic } from "../Admin/Admin_Logic.vue";

const { validateJson } = useAdminLogic(useAdminState());

const SERIES = JSON.stringify([{
    title: "오디세이",
    category: "고전문학",
    status: "review",
    parts: [
        { title: "제1권 · 아테나의 방문", content: "본문 1" },
        { title: "제2권 · 텔레마코스의 출항", content: "본문 2" },
    ],
}]);

describe("관리자 JSON 사전 검사", () => {
    it("라이브러리는 parts로 된 시리즈를 받는다", () => {
        const result = validateJson(SERIES, { allowParts: true });

        expect(result.errors).toEqual([]);
        expect(result.isValid).toBe(true);
        // 작품 하나다 — 부가 24개여도 등록되는 작품은 하나다.
        expect(result.itemCount).toBe(1);
    });

    it("부 수를 미리보기에 적는다", () => {
        // 24부를 붙여넣고 "1개 항목 인식됨"만 보면 다 들어갔는지 알 수 없다.
        const result = validateJson(SERIES, { allowParts: true });

        expect(result.previewTitles).toEqual(["오디세이 (2부)"]);
    });

    it("라이브러리는 parts 없는 단권도 그대로 받는다", () => {
        const single = JSON.stringify([{ title: "도덕경", content: "도가도 비상도" }]);

        const result = validateJson(single, { allowParts: true });

        expect(result.errors).toEqual([]);
        expect(result.previewTitles).toEqual(["도덕경"]);
    });

    it("부에 content가 빠지면 몇 번째 부인지 알려준다", () => {
        const broken = JSON.stringify([{
            title: "오디세이",
            parts: [
                { title: "제1권", content: "본문 1" },
                { title: "제2권" },
            ],
        }]);

        const result = validateJson(broken, { allowParts: true });

        expect(result.isValid).toBe(false);
        expect(result.errors).toContain("1번째 항목의 2번째 부에 content가 없습니다.");
    });

    it("parts가 빈 배열이면 거절한다", () => {
        const result = validateJson(JSON.stringify([{ title: "오디세이", parts: [] }]), { allowParts: true });

        expect(result.isValid).toBe(false);
        expect(result.errors).toContain("1번째 항목의 parts가 비어 있습니다.");
    });

    it("라이브러리에서 둘 다 없으면 parts도 쓸 수 있다고 알려준다", () => {
        const result = validateJson(JSON.stringify([{ title: "제목만" }]), { allowParts: true });

        expect(result.errors).toContain("1번째 항목에 content 또는 parts가 없습니다.");
    });

    it("뉴스는 parts를 넣어도 content를 계속 요구한다", () => {
        // 뉴스 기사에는 부라는 개념이 없다. 여기서 parts를 받아 주면
        // 백엔드가 content를 못 찾아 조용히 버린다.
        const result = validateJson(SERIES);

        expect(result.isValid).toBe(false);
        expect(result.errors).toContain("1번째 항목에 content 필드가 없습니다.");
    });

    it("코드펜스가 붙어 있어도 벗겨서 읽는다", () => {
        const fenced = "```json\n" + SERIES + "\n```";

        expect(validateJson(fenced, { allowParts: true }).isValid).toBe(true);
    });
});
