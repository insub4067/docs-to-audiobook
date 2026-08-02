let db = null;

// ----------------------------------------------------
// 0. IndexedDB Utility Module (Browser Local Storage)
// ----------------------------------------------------
function initDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("AudiobookMakerDB", 1);

        request.onerror = (event) => {
            console.error("Database error: ", event.target.error);
            showToast("DB를 열 수 없습니다.", "error");
            reject(event.target.error);
        };

        request.onsuccess = (event) => {
            db = event.target.result;
            resolve(db);
        };

        request.onupgradeneeded = (event) => {
            const dbInstance = event.target.result;
            if (!dbInstance.objectStoreNames.contains("audiobooks")) {
                dbInstance.createObjectStore("audiobooks", { keyPath: "id" });
            }
        };
    });
}

function saveAudiobookToDB(entry) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.put(entry);

        request.onsuccess = () => resolve();
        request.onerror = (e) => reject(e.target.error);
    });
}
function getAllAudiobooksFromDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(["audiobooks"], "readonly");
        const store = transaction.objectStore("audiobooks");
        const request = store.getAll();

        request.onsuccess = (e) => {
            const list = e.target.result || [];
            // 기본 제공 오디오북은 항상 최상단에 고정
            list.sort((a, b) => {
                if (!!a.isDefault !== !!b.isDefault) return a.isDefault ? -1 : 1;
                return b.timestamp - a.timestamp;
            });
            resolve(list);
        };
        request.onerror = (e) => reject(e.target.error);
    });
}

function deleteAudiobookFromDB(id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.delete(id);

        request.onsuccess = () => resolve();
        request.onerror = (e) => reject(e.target.error);
    });
}

function updateAudiobookPosition(id, lastPosition) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(["audiobooks"], "readwrite");
        const store = transaction.objectStore("audiobooks");
        const request = store.get(id);

        request.onsuccess = (e) => {
            const data = e.target.result;
            if (data) {
                data.lastPosition = lastPosition;
                data.playbackUpdatedAt = Date.now();
                store.put(data);
            }
            resolve(data);
        };
        request.onerror = (e) => reject(e.target.error);
    });
}

function getAudiobookFromDB(id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(["audiobooks"], "readonly");
        const store = transaction.objectStore("audiobooks");
        const request = store.get(id);
        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => reject(e.target.error);
    });
}
