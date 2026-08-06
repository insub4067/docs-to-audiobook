// 문장 북마크는 localStorage에 둔다.
//
// IndexedDB에 스토어를 추가하려면 DB 버전을 올려야 하는데, 다른 탭이 이전
// 버전을 붙들고 있으면 업그레이드가 막히고 open이 영영 끝나지 않는다.
// 앱 초기화가 그 promise를 기다리므로 화면이 통째로 빈 채로 멈춘다(실제로
// 겪었다 — 탭 두 개만 열려 있어도 재현된다). 북마크는 문장 한 줄짜리
// 텍스트라 용량이 작아 localStorage로 충분하고, 이런 위험이 없다.

/** 개인 오디오북(IndexedDB id)과 라이브러리 작품(서버 id) 모두 담는다
 *  — 둘 다 안정적인 id를 갖고 있어 같은 저장소로 다룰 수 있다. */
export interface BookmarkRecord {
    audiobookId: string;
    sentenceIndex: number;
    text: string;
    /** 북마크한 지점의 재생 시각(초). 눌렀을 때 여기서 이어 듣는다. */
    seconds: number;
    createdAt: number;
}

const STORAGE_PREFIX = "textAudio_bookmarks:";

function storageKey(audiobookId: string): string {
    return `${STORAGE_PREFIX}${audiobookId}`;
}

/** 한 작품의 북마크를 문장 순서대로 돌려준다. */
export function getBookmarks(audiobookId: string): BookmarkRecord[] {
    try {
        const raw = localStorage.getItem(storageKey(audiobookId));
        const list: BookmarkRecord[] = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(list)) return [];
        return [...list].sort((a, b) => a.sentenceIndex - b.sentenceIndex);
    } catch {
        // 손상된 값 하나 때문에 기능 전체가 죽지 않게 한다.
        return [];
    }
}

function write(audiobookId: string, list: BookmarkRecord[]): void {
    if (list.length === 0) {
        localStorage.removeItem(storageKey(audiobookId));
        return;
    }
    localStorage.setItem(storageKey(audiobookId), JSON.stringify(list));
}

/** 이미 있으면 지우고, 없으면 넣는다. 저장됐으면 true. */
export function toggleBookmark(bookmark: BookmarkRecord): boolean {
    const list = getBookmarks(bookmark.audiobookId);
    const existing = list.findIndex((b) => b.sentenceIndex === bookmark.sentenceIndex);
    if (existing >= 0) {
        list.splice(existing, 1);
        write(bookmark.audiobookId, list);
        return false;
    }
    list.push(bookmark);
    write(bookmark.audiobookId, list);
    return true;
}

export function removeBookmarkAt(audiobookId: string, sentenceIndex: number): void {
    write(audiobookId, getBookmarks(audiobookId).filter((b) => b.sentenceIndex !== sentenceIndex));
}
