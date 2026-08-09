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
    client_errors_7d?: number;
    synthesis_characters_30d?: number;
    synthesis_failed_characters_30d?: number;
    synthesis_estimated_usd_30d?: number;
    /** 활성 사용자 한 명이 30일간 만드는 TTS 비용(USD). 요금제를 정할 때 보는 값이다. */
    tts_cost_per_active_user_usd?: number | null;
}

export type AdminMetricName = keyof AdminMetrics;
