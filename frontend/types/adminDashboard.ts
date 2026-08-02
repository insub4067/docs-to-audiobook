// routes/system.py의 load_admin_metrics()가 돌려주는 형태와 맞춘다.
export interface AdminMetrics {
    total_users?: number;
    new_users_7d?: number;
    total_audiobooks?: number;
    daily_active_users?: number;
    weekly_active_users?: number;
    generation_started_30d?: number;
    generation_completed_30d?: number;
    generation_failed_30d?: number;
    generation_success_rate?: number | null;
    playback_started_30d?: number;
    week_one_retention_rate?: number | null;
    retention_cohort_size?: number;
}

export type AdminMetricName = keyof AdminMetrics;
