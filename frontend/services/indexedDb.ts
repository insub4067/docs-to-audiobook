// static/js/db.js를 그대로 옮긴다. 화면/기능 단위 View-State-Logic 분할과
// 달리, 이건 UI 상태가 없는 순수 데이터 접근 계층이라 3분할하지 않는다.
export interface AudiobookRecord {
    id: string;
    title: string;
    audioData?: ArrayBuffer | Blob | null;
    sentences?: unknown[];
    headings?: unknown[];
    timestamp?: number;
    dateString?: string;
    sizeBytes?: number;
    charCount?: number;
    isDefault?: boolean;
    version?: string;
    cloudId?: string;
    cloudOnly?: boolean;
    audioUrl?: string;
    sentencesUrl?: string;
    shareId?: string;
    shareExpiry?: number;
    lastPosition?: number;
    playbackSpeed?: number;
    repeatMode?: string;
    playbackUpdatedAt?: number;
    [key: string]: unknown;
}

let db: IDBDatabase | null = null;

export function initDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("AudiobookMakerDB", 1);

        request.onerror = (event) => {
            console.error("Database error: ", (event.target as IDBOpenDBRequest).error);
            reject((event.target as IDBOpenDBRequest).error);
        };

        request.onsuccess = (event) => {
            db = (event.target as IDBOpenDBRequest).result;
            resolve(db);
        };

        request.onupgradeneeded = (event) => {
            const dbInstance = (event.target as IDBOpenDBRequest).result;
            if (!dbInstance.objectStoreNames.contains("audiobooks")) {
                dbInstance.createObjectStore("audiobooks", { keyPath: "id" });
            }
        };
    });
}

function requireDb(): IDBDatabase {
    if (!db) throw new Error("IndexedDB가 아직 초기화되지 않았습니다. initDB()를 먼저 호출하세요.");
    return db;
}

export function saveAudiobookToDB(entry: AudiobookRecord): Promise<void> {
    return new Promise((resolve, reject) => {
        const transaction = requireDb().transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.put(entry);

        request.onsuccess = () => resolve();
        request.onerror = (e) => reject((e.target as IDBRequest).error);
    });
}

export function getAllAudiobooksFromDB(): Promise<AudiobookRecord[]> {
    return new Promise((resolve, reject) => {
        const transaction = requireDb().transaction(["audiobooks"], "readonly");
        const store = transaction.objectStore("audiobooks");
        const request = store.getAll();

        request.onsuccess = (e) => {
            const list: AudiobookRecord[] = (e.target as IDBRequest).result || [];
            // 기본 제공 오디오북은 항상 최상단에 고정
            list.sort((a, b) => {
                if (!!a.isDefault !== !!b.isDefault) return a.isDefault ? -1 : 1;
                return (b.timestamp || 0) - (a.timestamp || 0);
            });
            resolve(list);
        };
        request.onerror = (e) => reject((e.target as IDBRequest).error);
    });
}

export function deleteAudiobookFromDB(id: string): Promise<void> {
    return new Promise((resolve, reject) => {
        const transaction = requireDb().transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.delete(id);

        request.onsuccess = () => resolve();
        request.onerror = (e) => reject((e.target as IDBRequest).error);
    });
}

export function updateAudiobookPosition(id: string, lastPosition: number): Promise<AudiobookRecord | undefined> {
    return new Promise((resolve, reject) => {
        const transaction = requireDb().transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.get(id);

        request.onsuccess = (e) => {
            const data = (e.target as IDBRequest).result;
            if (data) {
                data.lastPosition = lastPosition;
                data.playbackUpdatedAt = Date.now();
                store.put(data);
            }
            resolve(data);
        };
        request.onerror = (e) => reject((e.target as IDBRequest).error);
    });
}

export function getAudiobookFromDB(id: string): Promise<AudiobookRecord | undefined> {
    return new Promise((resolve, reject) => {
        const transaction = requireDb().transaction(["audiobooks"], "readonly");
        const store = transaction.objectStore("audiobooks");
        const request = store.get(id);
        request.onsuccess = (e) => resolve((e.target as IDBRequest).result);
        request.onerror = (e) => reject((e.target as IDBRequest).error);
    });
}
