import { createApp } from "vue";
import { createPinia } from "pinia";
import router from "./router";
import App from "./App.vue";
import { initDB } from "./services/indexedDb";

const app = createApp(App);
app.use(createPinia());
app.use(router);

// 자식 컴포넌트의 onMounted는 부모보다 먼저 실행되므로, 어떤 화면이든
// 마운트 시점에 바로 IndexedDB를 조회해도 안전하도록 마운트 전에
// 초기화를 끝낸다.
initDB().then(() => app.mount("#app"));
