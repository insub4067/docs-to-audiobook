// GET /api/config를 한 번만 받아 재사용한다.
//
// 이 파일이 존재하는 이유는 캐싱보다 **단일 출처**에 있다. 업로드 상한 같은
// 값을 프론트가 따로 들고 있으면 백엔드와 조용히 어긋난다 — 실제로 관리자
// 상한이 백엔드 250MB인데 프론트가 50MB로 막고 있었고, 아무 오류도 나지
// 않아서 그동안 몰랐다. 서버가 말하는 값만 쓴다.

export interface AppConfig {
    providers: Record<string, string>;
    google_client_id: string;
    google_api_key: string;
    upload_limit_bytes: number;
    admin_upload_limit_bytes: number;
}

// 설정은 배포마다 고정이라 한 번만 받으면 된다. 실패한 약속은 캐시하지
// 않는다 — 일시적 네트워크 오류가 세션 내내 굳어버리면 안 된다.
let inFlight: Promise<AppConfig> | null = null;

export function loadAppConfig(): Promise<AppConfig> {
    if (!inFlight) {
        inFlight = fetch("/api/config")
            .then((response) => {
                if (!response.ok) throw new Error(`설정을 불러오지 못했습니다 (${response.status})`);
                return response.json();
            })
            .catch((error) => {
                inFlight = null;
                throw error;
            });
    }
    return inFlight;
}

/** 테스트에서 호출 간 캐시가 새지 않게 한다. */
export function resetAppConfigCache(): void {
    inFlight = null;
}

/**
 * 업로드 전 클라이언트가 미리 걸러줄 상한(바이트).
 *
 * 설정을 못 받았으면 **null**을 준다. 이때는 미리 거르지 않고 그냥 올린다 —
 * 진짜 상한은 서버가 업로드 스트림에서 강제하고(413), 여기서 임의의
 * 기본값을 정해두면 그게 다시 두 번째 출처가 된다.
 */
export async function uploadLimitBytes(isAdmin: boolean): Promise<number | null> {
    try {
        const config = await loadAppConfig();
        const limit = isAdmin ? config.admin_upload_limit_bytes : config.upload_limit_bytes;
        return typeof limit === "number" ? limit : null;
    } catch {
        return null;
    }
}
