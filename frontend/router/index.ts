import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import AdminDashboardView from '../AdminDashboard/AdminDashboard_View.vue';
import AdminMetricView from '../AdminDashboard/AdminMetric_View.vue';
import HomeView from '../views/Home_View.vue';

const routes: RouteRecordRaw[] = [
  { 
    path: '/', 
    component: HomeView 
  },
  { 
    path: '/admin', 
    component: AdminDashboardView 
  },
  { 
    path: '/admin/metrics/:metricName', 
    component: AdminMetricView 
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
