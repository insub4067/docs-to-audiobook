import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import AdminApp from "./AdminDashboard/AdminApp.vue";
import AdminDashboardView from "./AdminDashboard/AdminDashboard_View.vue";
import AdminMetricView from "./AdminDashboard/AdminMetric_View.vue";

const routes = [
  { path: "/admin", component: AdminDashboardView },
  { path: "/admin/metrics/:metricName", component: AdminMetricView },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

const app = createApp(AdminApp);
app.use(router);
app.mount("#app");
