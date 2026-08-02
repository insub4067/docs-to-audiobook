<script setup lang="ts">
import { computed } from "vue";
import type { PwaState } from "./Pwa_State.vue";

const props = defineProps<{ state: PwaState }>();

const SPOKE_COUNT = 12;
const litCount = computed(() => Math.round(props.state.pullProgress.value * SPOKE_COUNT));
</script>

<template>
    <div class="pull-refresh" aria-hidden="true" :class="{ settling: state.isPullSettling.value, refreshing: state.isRefreshing.value }" :style="{ opacity: state.pullOpacity.value }">
        <div class="pull-spinner">
            <i v-for="n in SPOKE_COUNT" :key="n" :style="{ opacity: n <= litCount ? 1 : 0.15 }"></i>
        </div>
    </div>
</template>
