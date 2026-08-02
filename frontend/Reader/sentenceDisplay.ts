// static/js/reader.js의 renderLocalSentences/openSharedReaderMode 안에 있던
// 문장 → 화면 표시 아이템(문단/제목/표) 변환 로직을 순수 함수로 뽑아낸 것.
// UI 상태가 없는 데이터 변환이라 View/State/Logic으로 나누지 않는다.
export interface ReaderSentence {
    text: string;
    start: number;
    end?: number;
    type?: string;
    display?: string;
    level?: number;
    table?: { id: string; row: number; column: number; header?: string };
}

export interface HeadingRef {
    text: string;
    level: number;
    sentIndex: number;
    startMs: number;
}

export type ReaderDisplayItem =
    | { kind: "sentence"; index: number; text: string }
    | { kind: "heading"; index: number; text: string; level: number }
    | { kind: "table"; columns: number; header: string[]; rows: Array<Array<{ index: number; text: string } | null>> };

function cleanDisplayText(text: string | undefined): string {
    let result = (text || "").replace(/[*_~`\\]/g, "");
    result = result.replace(/^#+\s*/, "");
    return result.trim();
}

function detectHeading(sentence: ReaderSentence): { isHeading: boolean; level: number; titleText: string } {
    const rawText = (sentence.text || "").trim();
    if (sentence.type === "heading" && sentence.display) {
        return { isHeading: true, level: sentence.level || 2, titleText: sentence.display };
    }
    const headingMatch = rawText.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
        return { isHeading: true, level: headingMatch[1].length, titleText: cleanDisplayText(headingMatch[2]) };
    }
    return { isHeading: false, level: 2, titleText: "" };
}

// supportTables: 로컬 생성 오디오북(open())만 표를 그린다 — 공유 리더 모드
// (openSharedReaderMode())는 원본에서도 표를 지원하지 않는다.
export function buildDisplayItems(sentences: ReaderSentence[], supportTables: boolean): { items: ReaderDisplayItem[]; headings: HeadingRef[] } {
    const items: ReaderDisplayItem[] = [];
    const headings: HeadingRef[] = [];

    for (let index = 0; index < sentences.length; index++) {
        const sentence = sentences[index];

        if (supportTables && sentence.table) {
            const tableId = sentence.table.id;
            const cells: Array<{ sentence: ReaderSentence; index: number }> = [];
            while (index < sentences.length && sentences[index].table?.id === tableId) {
                cells.push({ sentence: sentences[index], index });
                index++;
            }
            index--;
            const columns = Math.max(...cells.map((cell) => cell.sentence.table!.column)) + 1;
            const headerCells = cells.filter((cell) => cell.sentence.table!.row === 0);
            const header: string[] = [];
            for (let column = 0; column < columns; column++) {
                header.push(headerCells.find((cell) => cell.sentence.table!.column === column)?.sentence.table!.header || "");
            }
            const rowNumbers = [...new Set(cells.map((cell) => cell.sentence.table!.row))];
            const rows = rowNumbers.map((row) => {
                const rowCells: Array<{ index: number; text: string } | null> = [];
                for (let column = 0; column < columns; column++) {
                    const cell = cells.find((c) => c.sentence.table!.row === row && c.sentence.table!.column === column);
                    if (!cell) { rowCells.push(null); continue; }
                    const text = cleanDisplayText(cell.sentence.text);
                    const prefix = `${cell.sentence.table!.header}:`;
                    rowCells.push({ index: cell.index, text: text.startsWith(prefix) ? text.slice(prefix.length).trim() : text });
                }
                return rowCells;
            });
            items.push({ kind: "table", columns, header, rows });
            continue;
        }

        const { isHeading, level, titleText } = detectHeading(sentence);
        if (isHeading && titleText) {
            items.push({ kind: "heading", index, text: titleText, level });
            headings.push({ text: titleText, level, sentIndex: index, startMs: sentence.start });
        } else {
            items.push({ kind: "sentence", index, text: cleanDisplayText(sentence.text) + " " });
        }
    }

    return { items, headings };
}

export function findActiveSentenceIndex(sentences: ReaderSentence[], currentMs: number): number {
    for (let index = 0; index < sentences.length; index++) {
        if (currentMs >= sentences[index].start && currentMs <= (sentences[index].end ?? Infinity)) return index;
    }
    if (sentences.length === 0) return -1;
    if (currentMs < sentences[0].start) return 0;
    for (let index = sentences.length - 1; index >= 0; index--) {
        if (currentMs >= sentences[index].start) return index;
    }
    return -1;
}
