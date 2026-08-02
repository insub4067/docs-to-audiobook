<script lang="ts">
import { ref, type Ref } from "vue";

export type PushButtonState = "on" | "off" | "blocked";

export interface NotificationsState {
    isPushVisible: Ref<boolean>;
    pushState: Ref<PushButtonState>;
    isPushBusy: Ref<boolean>;
}

export function useNotificationsState(): NotificationsState {
    return {
        isPushVisible: ref(false),
        pushState: ref("off"),
        isPushBusy: ref(false),
    };
}

export default {};
</script>
