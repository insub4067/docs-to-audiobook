import { ref } from 'vue';

export interface ActionSheetOption {
  label: string;
  icon?: string;
  isDanger?: boolean;
  action: () => void | Promise<void>;
}

export interface ActionSheetState {
  isVisible: boolean;
  title?: string;
  options: ActionSheetOption[];
}

const state = ref<ActionSheetState>({
  isVisible: false,
  options: []
});

export function useActionSheet() {
  function show(options: ActionSheetOption[], title?: string) {
    state.value.options = options;
    state.value.title = title;
    state.value.isVisible = true;
  }

  function hide() {
    state.value.isVisible = false;
  }

  return {
    state,
    show,
    hide
  };
}
