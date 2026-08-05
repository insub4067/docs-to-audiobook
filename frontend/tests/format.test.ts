import { describe, it, expect } from "vitest";
import { formatBytes, formatTime, getAudiobookDisplayTitle } from "../utils/format";

// 재생 시간 라벨. 오디오가 아직 로드되기 전 duration은 NaN이고, 스트리밍
// 중에는 Infinity가 나올 수 있다 — 그대로 찍히면 "NaN:NaN"이 화면에 뜬다.
describe("formatTime", () => {
    it("mm:ss로 0을 채워 표시한다", () => {
        expect(formatTime(0)).toBe("00:00");
        expect(formatTime(5)).toBe("00:05");
        expect(formatTime(65)).toBe("01:05");
        expect(formatTime(600)).toBe("10:00");
    });

    it("초 단위는 내림한다", () => {
        expect(formatTime(59.9)).toBe("00:59");
    });

    it("60분이 넘어도 분으로 계속 센다", () => {
        expect(formatTime(3661)).toBe("61:01");
    });

    it("NaN과 Infinity는 00:00으로 막는다", () => {
        expect(formatTime(NaN)).toBe("00:00");
        expect(formatTime(Infinity)).toBe("00:00");
    });
});

describe("getAudiobookDisplayTitle", () => {
    it("확장자를 떼고 보여준다", () => {
        expect(getAudiobookDisplayTitle("데미안.pdf")).toBe("데미안");
        expect(getAudiobookDisplayTitle("report.docx")).toBe("report");
    });

    it("확장자가 없으면 그대로 둔다", () => {
        expect(getAudiobookDisplayTitle("제목만 있는 글")).toBe("제목만 있는 글");
    });

    it("제목 중간의 점은 건드리지 않고 마지막 확장자만 뗀다", () => {
        expect(getAudiobookDisplayTitle("v1.2 초안.pdf")).toBe("v1.2 초안");
    });
});

describe("formatBytes", () => {
    it("0은 그대로 표기한다", () => {
        expect(formatBytes(0)).toBe("0 Bytes");
    });

    it("단위를 올려 가며 표기한다", () => {
        expect(formatBytes(1024)).toBe("1 KB");
        expect(formatBytes(1024 * 1024)).toBe("1 MB");
        expect(formatBytes(1024 * 1024 * 1024)).toBe("1 GB");
    });

    it("소수 자릿수를 조절할 수 있다", () => {
        expect(formatBytes(1536, 1)).toBe("1.5 KB");
        expect(formatBytes(1536, 0)).toBe("2 KB");
    });
});
