// 업로드 진행률을 알려주는 POST.
//
// fetch는 업로드 진행률을 주지 않는다 — 요청 본문을 얼마나 보냈는지 알 방법이
// 없다(ReadableStream 본문은 iOS Safari가 지원하지 않는다). XMLHttpRequest만
// upload.onprogress로 바이트 단위 실측을 준다. 큰 PDF를 모바일에서 올리면
// 이 전송 구간이 대기 시간의 상당 부분이라, 여기만이라도 진짜 숫자를 보여준다.
//
// 서버가 파일을 받은 뒤 텍스트를 뽑는 구간은 진행률을 알 수 없다(응답이 한
// 번에 오고 중간 상태를 스트리밍하지 않는다). 그 구간은 percent를 null로
// 넘겨 화면이 가짜 막대를 채우지 않게 한다.
//
// 취소는 기존 AbortController를 그대로 받는다. 호출부의 cancelUpload와
// isAbortError를 손대지 않으려고 DOMException("AbortError")로 맞춰 거절한다.

/** percent는 0~100, 전송이 끝나 서버 처리로 넘어가면 null. */
export type UploadProgressHandler = (percent: number | null) => void;

export function postFormWithProgress(
    url: string,
    formData: FormData,
    headers: Record<string, string>,
    signal: AbortSignal,
    onProgress: UploadProgressHandler,
): Promise<unknown> {
    return new Promise((resolve, reject) => {
        const abortError = () => new DOMException("업로드를 취소했습니다.", "AbortError");
        if (signal.aborted) {
            reject(abortError());
            return;
        }

        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);
        // Content-Type은 넣지 않는다 — multipart 경계 문자열은 브라우저가 정한다.
        for (const [name, value] of Object.entries(headers)) {
            xhr.setRequestHeader(name, value);
        }

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable && event.total > 0) {
                onProgress(Math.round((event.loaded / event.total) * 100));
            }
        };
        // 본문을 다 보낸 시점. 여기부터 응답이 올 때까지가 서버 처리 구간이다.
        xhr.upload.onload = () => onProgress(null);

        xhr.onload = () => {
            let body: { detail?: string } | null = null;
            try {
                body = JSON.parse(xhr.responseText);
            } catch {
                body = null;
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(body);
                return;
            }
            reject(new Error(body?.detail || "텍스트 추출 실패"));
        };
        xhr.onerror = () => reject(new Error("네트워크가 끊겨 업로드하지 못했습니다."));
        xhr.ontimeout = () => reject(new Error("업로드가 시간 안에 끝나지 않았습니다."));

        signal.addEventListener("abort", () => {
            xhr.abort();
            reject(abortError());
        }, { once: true });

        xhr.send(formData);
    });
}
