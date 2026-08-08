<script setup lang="ts">
// 목록 한 줄이 도착하기 전에 자리만 잡아 두는 행. 경제 뉴스·서점·홈 목록이
// 같은 .audio-item 골격을 쓰므로 하나로 공유한다.
//
// 예전에는 목록이 오기 전까지 아무것도 없다가 갑자기 나타났다. 그러면 그
// 아래 내용이 통째로 밀려, 누르려던 것이 손가락 밑에서 움직인다.
//
// 실제 행과 같은 골격(아이콘 + 제목 + 부제)을 회색 블록으로 먼저 그려 두면
// 도착했을 때 같은 자리에 글자만 들어차므로 화면이 뛰지 않는다.
defineProps<{
    /** 제목 줄의 너비. 여러 줄을 나란히 둘 때 조금씩 달라야 실제 목록처럼 보인다. */
    titleWidth?: string;
}>();
</script>

<template>
    <div class="audio-item audio-item-news list-row-placeholder" aria-hidden="true">
        <div class="audio-item-front">
            <div class="audio-title-group">
                <span class="redacted redacted-icon"></span>
                <div class="audio-title-col">
                    <span class="redacted redacted-title" :style="{ width: titleWidth ?? '82%' }"></span>
                    <span class="redacted redacted-subtitle"></span>
                </div>
            </div>
        </div>
    </div>
</template>
