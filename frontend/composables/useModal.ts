import { ref, type Ref } from 'vue';

export interface ModalState {
  isVisible: boolean;
  title: string;
  component: string | null;
  props: Record<string, any>;
}

const state = ref<ModalState>({
  isVisible: false,
  title: '',
  component: null,
  props: {}
});

export function useModal() {
  function show(componentName: string, title: string, props: Record<string, any> = {}) {
    state.value.component = componentName;
    state.value.title = title;
    state.value.props = props;
    state.value.isVisible = true;
  }

  function hide() {
    state.value.isVisible = false;
    setTimeout(() => {
      // delay component destruction until animation finishes
      if (!state.value.isVisible) {
        state.value.component = null;
      }
    }, 300);
  }

  return {
    state,
    show,
    hide
  };
}
