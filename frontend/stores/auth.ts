import { defineStore } from "pinia";

export interface AuthUser {
    id: string;
    email: string;
    full_name?: string | null;
    avatar_url?: string | null;
    is_admin: boolean;
    created_at?: string | null;
}

export interface AuthStoreState {
    user: AuthUser | null;
    token: string | null;
}

// static/js/auth.js의 currentAuthenticatedUserId + localStorage("authToken")를
// 대신하는 전역 반응형 상태. isLoggedIn/isAdmin은 user·token으로부터
// 계산되므로 별도로 저장하지 않는다(그래야 어긋날 일이 없다).
export const useAuthStore = defineStore("auth", {
    state: (): AuthStoreState => ({
        user: null,
        token: null,
    }),
    getters: {
        isLoggedIn: (state) => !!(state.user && state.token),
        isAdmin: (state) => !!(state.user && state.token && state.user.is_admin === true),
    },
    actions: {
        setSession(user: AuthUser | null, token: string | null) {
            this.user = user;
            this.token = token;
        },
        clearSession() {
            this.user = null;
            this.token = null;
        },
    },
});
