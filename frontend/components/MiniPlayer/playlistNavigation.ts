// 재생목록(폴더에 묶인 오디오북 / 경제 뉴스 / 서점 시리즈의 부)에서 앞뒤로
// 옮겨 다니는 로직.
//
// 재생목록 시트와 미니 플레이어 스와이프가 같은 목록·같은 현재 위치를 봐야
// 해서 여기로 모았다. 시트에만 두면 미니 플레이어가 목록을 다시 계산하게
// 되고, 둘이 어긋나면 "시트에서는 3번째인데 스와이프하면 5번째로 간다"
// 같은 일이 생긴다.
import { computed, type ComputedRef } from "vue";
import type { ReaderState } from "../../Reader/Reader_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import type { AudioListState } from "../Library/AudioList_State.vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import { useNewsState, type NewsItem } from "../News/News_State.vue";
import { useNewsLogic } from "../News/News_Logic.vue";
import { useLibraryState, type LibraryPart } from "../../Library/Library_State.vue";
import { useLibraryLogic } from "../../Library/Library_Logic.vue";

export type PlaylistItem = AudiobookRecord | NewsItem | LibraryPart;

export interface PlaylistOpenOptions {
    /** 미니 플레이어에서 넘길 때처럼 읽기 화면을 펼치지 않아야 하는 경우 false. */
    openReaderUI?: boolean;
}

export function isLibraryPart(item: PlaylistItem): item is LibraryPart {
    return "part_number" in item;
}

export function isNewsItem(item: PlaylistItem): item is NewsItem {
    // ⚠️ 부(LibraryPart)도 audio_url을 갖는다. 부를 먼저 걸러내야
    // 서점 시리즈가 뉴스로 잘못 잡히지 않는다.
    return !isLibraryPart(item) && "audio_url" in item;
}

export interface PlaylistNavigation {
    items: ComputedRef<PlaylistItem[]>;
    currentIndex: ComputedRef<number>;
    open(item: PlaylistItem, options?: PlaylistOpenOptions): void;
    /** offset이 -1이면 이전, +1이면 다음. 목록 밖이면 아무 일도 하지 않는다. */
    goToOffset(offset: number, options?: PlaylistOpenOptions): boolean;
}

export function usePlaylistNavigation(
    readerState: ReaderState,
    audioListState: AudioListState,
    readerLogic: ReaderLogic,
): PlaylistNavigation {
    const newsState = useNewsState();
    const newsLogic = useNewsLogic(newsState, readerLogic);
    const libraryState = useLibraryState();
    const libraryLogic = useLibraryLogic(libraryState, readerLogic);

    const isNewsPlaylist = computed(() => readerState.sharedPlaylistKind.value === "news");
    const isLibraryPlaylist = computed(() => readerState.sharedPlaylistKind.value === "library");

    // 폴더든 뉴스든 시리즈든 "같이 묶인 항목이 2개 이상"일 때만 옮겨 다닐
    // 의미가 있다.
    const items = computed<PlaylistItem[]>(() => {
        if (isNewsPlaylist.value) return newsState.items.value;
        if (isLibraryPlaylist.value) return libraryState.queueParts.value;
        const folderId = readerState.currentAudioObject.value?.folderId;
        if (!folderId) return [];
        return audioListState.savedAudiobooks.value.filter((audio) => audio.folderId === folderId);
    });

    // 뉴스와 시리즈는 큐가 위치를 들고 있다(개별 항목을 눌러 들어도 채워진다).
    // 폴더 항목은 지금 열려 있는 오디오북의 id로 찾는다.
    const currentIndex = computed(() => {
        if (isNewsPlaylist.value) return newsState.queueIndex.value;
        if (isLibraryPlaylist.value) return libraryState.queueIndex.value;
        const currentId = readerState.currentAudioObject.value?.id;
        return currentId ? items.value.findIndex((item) => item.id === currentId) : -1;
    });

    function open(item: PlaylistItem, options: PlaylistOpenOptions = {}): void {
        const openReaderUI = options.openReaderUI ?? true;
        if (isLibraryPart(item)) libraryLogic.playQueuePartAt(items.value.indexOf(item), { openReaderUI });
        else if (isNewsItem(item)) newsLogic.openNewsItem(item, items.value.indexOf(item), { openReaderUI });
        else readerLogic.open(item, { openReaderUI });
    }

    function goToOffset(offset: number, options: PlaylistOpenOptions = {}): boolean {
        const target = currentIndex.value + offset;
        if (currentIndex.value < 0 || target < 0 || target >= items.value.length) return false;
        open(items.value[target], options);
        return true;
    }

    return { items, currentIndex, open, goToOffset };
}
