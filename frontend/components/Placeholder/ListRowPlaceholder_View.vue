<script setup lang="ts">
// 목록 한 줄이 도착하기 전에 자리만 잡아 두는 행. 경제 뉴스·서점·홈 목록이
// 같은 .audio-item 골격을 쓰므로 하나로 공유한다.
//
// 목록이 늦게 오면 그 아래 내용이 통째로 밀려, 누르려던 것이 손가락 밑에서
// 움직인다. 그래서 올 자리를 미리 잡아 둔다.
//
// ⚠️ 회색 막대의 크기를 직접 잡지 않는다. 그렇게 했더니 계속 어긋났다 —
//    처음엔 제목을 한 줄로 가정해 37px 짧았고, 두 줄로 고치니 마진이 상쇄돼
//    5px 짧았고, 마진을 패딩으로 바꾸니 이번엔 블록 자식 사이의 공백
//    텍스트가 만든 줄상자 때문에 22px 길었다.
//
//    대신 **실제 글자를 넣고 그 위를 덮는다.** 글자가 들어 있으니 줄 높이도
//    줄바꿈도 실제 행과 똑같이 계산되고, 글꼴 크기 설정을 바꿔도 따라온다.
//    SwiftUI의 .redacted(reason: .placeholder)와 같은 방식이다.
withDefaults(defineProps<{
    /** 제목 자리를 채울 글자. 길이가 곧 줄 수라, 실제 제목과 비슷하게 준다. */
    titleFiller?: string;
    subtitleFiller?: string;
}>(), {
    // 경제 뉴스·서점 제목은 대개 두 줄로 감긴다.
    titleFiller: "불러오는 중입니다 잠시만 기다려 주세요 곧 목록이 표시됩니다",
    subtitleFiller: "출처 · 시간",
});
</script>

<template>
    <div class="audio-item audio-item-news list-row-placeholder" aria-hidden="true">
        <div class="audio-item-front">
            <div class="audio-title-group">
                <span class="redacted redacted-icon"></span>
                <div class="audio-title-col">
                    <span class="audio-title redacted-text">{{ titleFiller }}</span>
                    <span class="audio-subtitle redacted-text">{{ subtitleFiller }}</span>
                </div>
            </div>
        </div>
    </div>
</template>
