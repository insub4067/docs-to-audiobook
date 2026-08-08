<script setup lang="ts">
// 경제 뉴스가 도착하기 전에 자리만 잡아 두는 행.
//
// 예전에는 목록이 오기 전까지 카드가 통째로 없었다가(v-if="topItem") 갑자기
// 나타났다. 홈에 들어오면 업로드 카드만 있다가 잠시 뒤 그 아래가 밀리면서
// 뉴스 카드가 끼어드는 셈이라, 누르려던 것이 움직이는 일이 생긴다.
//
// 그래서 실제 행과 같은 골격(아이콘 + 제목 + 부제 두 줄)을 회색 블록으로
// 먼저 그려 둔다. 도착하면 같은 자리에 글자만 들어차므로 화면이 뛰지 않는다.
defineProps<{
    /** 제목 줄의 너비. 여러 줄을 나란히 둘 때 조금씩 달라야 실제 목록처럼 보인다. */
    titleWidth?: string;
}>();
</script>

<template>
    <div class="audio-item audio-item-news news-placeholder" aria-hidden="true">
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
