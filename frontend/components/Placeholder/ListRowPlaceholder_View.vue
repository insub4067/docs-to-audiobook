<script setup lang="ts">
// 목록 한 줄이 도착하기 전에 자리만 잡아 두는 행. 경제 뉴스·서점·홈 목록이
// 같은 .audio-item 골격을 쓰므로 하나로 공유한다.
//
// 예전에는 목록이 오기 전까지 아무것도 없다가 갑자기 나타났다. 그러면 그
// 아래 내용이 통째로 밀려, 누르려던 것이 손가락 밑에서 움직인다.
//
// ⚠️ 회색 블록을 .audio-title / .audio-subtitle **안에** 넣는다. 블록 크기를
//    직접 지정하면 실제 행과 높이가 어긋난다 — 처음엔 제목을 한 줄로 잡았다가
//    실제 행(108px)보다 37px 짧아서, 자리를 잡아 두고도 그만큼 밀렸다.
//    실제 클래스 안에 넣으면 글꼴 크기·줄 높이를 그대로 물려받아, 글자 크기
//    설정이 바뀌어도 계속 맞는다.
withDefaults(defineProps<{
    /** 제목이 몇 줄로 감기는지. 뉴스 제목은 보통 두 줄이다. */
    titleLines?: number;
    /** 제목 줄의 너비. 여러 줄을 나란히 둘 때 조금씩 달라야 목록처럼 보인다. */
    titleWidth?: string;
}>(), {
    titleLines: 2,
    titleWidth: "82%",
});
</script>

<template>
    <div class="audio-item audio-item-news list-row-placeholder" aria-hidden="true">
        <div class="audio-item-front">
            <div class="audio-title-group">
                <span class="redacted redacted-icon"></span>
                <div class="audio-title-col">
                    <span class="audio-title">
                        <span
                            v-for="line in titleLines"
                            :key="line"
                            class="redacted redacted-line"
                            :style="{ width: line === titleLines ? '54%' : titleWidth }"
                        ></span>
                    </span>
                    <span class="audio-subtitle">
                        <span class="redacted redacted-line" style="width: 45%"></span>
                    </span>
                </div>
            </div>
        </div>
    </div>
</template>
