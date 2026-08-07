// 서명 URL이 만료되기 전에 목록을 다시 받아 오기 위한 공용 규칙.
//
// 뉴스와 라이브러리 항목의 audio_url/sentences_url은 Supabase Storage의
// **서명 URL**이고 유효시간이 1시간이다(backend/state.py SIGNED_URL_TTL).
// 목록 응답을 만들 때 서명하므로, 목록을 오래 들고 있으면 그 안의 URL이
// 통째로 죽는다.
//
// 실제로 그렇게 깨졌다. 홈의 경제 뉴스는 앱을 켤 때 딱 한 번만 목록을
// 받아 왔고(`if (!loaded) loadNews()`), PWA는 며칠씩 열려 있다. 한 시간이
// 지난 뒤 기사를 누르면 오디오도 문장도 404가 나서, 빈 본문에 00:00만
// 뜨고 "공유 오디오를 불러올 수 없습니다"가 떴다.
//
// 만료 직전에 갱신하면 재생을 누르는 순간 만료되는 경계 사례가 남는다.
// 유효시간의 절반쯤에서 미리 갱신해 그 창을 없앤다.
const SIGNED_URL_TTL_MS = 60 * 60 * 1000;
export const SIGNED_URL_REFRESH_AFTER_MS = SIGNED_URL_TTL_MS / 2;

/** 마지막으로 목록을 받아 온 시각(Date.now()) 기준으로 갱신이 필요한가. */
export function needsFreshSignedUrls(fetchedAt: number): boolean {
    if (!fetchedAt) return true;
    return Date.now() - fetchedAt >= SIGNED_URL_REFRESH_AFTER_MS;
}
