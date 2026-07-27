import re

with open("static/app.js", "r") as f:
    content = f.read()

# 1. Restore openIndexSheet before performShare
index_sheet_code = """
    function openIndexSheet(headings) {
        const indexSheetList = document.getElementById("indexSheetList");
        const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
        if (!indexSheetList) return;
        indexSheetList.innerHTML = "";

        headings.forEach(item => {
            const div = document.createElement("div");
            div.className = `index-item h${item.level}`;
            
            // h1, h2, h3 시각적 구분 접두사
            const prefix = item.level === 1 ? "• " : (item.level === 2 ? "└ " : "  └ ");
            div.textContent = prefix + (item.text || item.display_text || item.display);

            div.addEventListener("click", () => {
                closeIndexSheet();
                // 해당 문장 위치로 오디오 이동 및 스크롤
                readerAudio.currentTime = (item.startMs || item.start) / 1000;
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                showPauseIcon();

                const targetSpan = document.getElementById(`sent-${item.sentIndex || item.sent_index}`);
                if (targetSpan) {
                    const spanTop = targetSpan.offsetTop;
                    const containerHeight = readerContent.clientHeight;
                    const targetScroll = spanTop - containerHeight / 2 + targetSpan.clientHeight / 2;
                    readerContent.scrollTo({ top: targetScroll, behavior: "smooth" });
                }
            });

            indexSheetList.appendChild(div);
        });

        indexSheetBackdrop.classList.add("show");
    }

    function closeIndexSheet() {
        const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
        if (indexSheetBackdrop) indexSheetBackdrop.classList.remove("show");
    }

    const indexSheetCancelBtn = document.getElementById("indexSheetCancelBtn");
    const indexSheetBackdrop = document.getElementById("indexSheetBackdrop");
    if (indexSheetCancelBtn) indexSheetCancelBtn.addEventListener("click", closeIndexSheet);
    if (indexSheetBackdrop) {
        indexSheetBackdrop.addEventListener("click", (e) => {
            if (e.target === indexSheetBackdrop) closeIndexSheet();
        });
    }

    async function performShare(target) {"""
content = content.replace("    async function performShare(target) {", index_sheet_code)

# 2. Patch openReaderMode
reader_target = """        // 문장 렌더링
        audio.sentences.forEach((s, index) => {
            const span = document.createElement("span");
            span.className = "reader-sentence";
            span.id = `sent-${index}`;
            span.textContent = s.text + " ";
            
            span.addEventListener("click", () => {
                readerAudio.currentTime = s.start / 1000;
                readerAudio.play().catch(err => console.log("Play failed:", err));
                showPauseIcon();
            });
            
            readerContent.appendChild(span);
        });"""

reader_replacement = """        // 문장 및 헤더 렌더링 & Index(목차) 데이터 구성
        const indexHeadings = [];

        function cleanDisplayText(text) {
            let t = (text || "").replace(/[*_~`\\\\]/g, '');
            t = t.replace(/^#+\\s*/, '');
            return t.trim();
        }

        audio.sentences.forEach((s, index) => {
            const rawText = (s.text || "").trim();
            
            let isHeading = false;
            let level = 2;
            let titleText = "";
            
            if (s.type === "heading" && s.display) {
                isHeading = true;
                level = s.level || 2;
                titleText = s.display;
            } else {
                const mdHeadingMatch = rawText.match(/^(#{1,3})\\s+(.+)$/);
                const boldHeadingMatch = rawText.match(/^(\\**|__)(.+?)\\1$/);
                const numberHeadingMatch = rawText.match(/^(\\**|__)?(\\d+[\\.\\\\s]+.+?)\\1?$/);

                if (mdHeadingMatch) {
                    isHeading = true;
                    level = mdHeadingMatch[1].length;
                    titleText = cleanDisplayText(mdHeadingMatch[2]);
                } else if (boldHeadingMatch && rawText.length < 60) {
                    isHeading = true;
                    level = 2;
                    titleText = cleanDisplayText(boldHeadingMatch[2]);
                } else if (numberHeadingMatch && rawText.length < 40) {
                    isHeading = true;
                    level = 3;
                    titleText = cleanDisplayText(rawText);
                }
            }

            if (isHeading && titleText) {
                const headingEl = document.createElement("h" + level);
                headingEl.className = "reader-heading h" + level;

                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = titleText;

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                headingEl.appendChild(span);
                readerContent.appendChild(headingEl);

                indexHeadings.push({
                    text: titleText,
                    level: level,
                    sentIndex: index,
                    startMs: s.start
                });
            } else {
                const span = document.createElement("span");
                span.className = "reader-sentence";
                span.id = "sent-" + index;
                span.textContent = cleanDisplayText(s.text) + " ";

                span.addEventListener("click", () => {
                    readerAudio.currentTime = s.start / 1000;
                    readerAudio.play().catch(err => console.log("Play failed:", err));
                    showPauseIcon();
                });

                readerContent.appendChild(span);
            }
        });

        // 목차(Index) 버튼 표시 제어
        const readerIndexBtn = document.getElementById("readerIndexBtn");
        if (readerIndexBtn) {
            const finalHeadings = (audio.headings && audio.headings.length > 0) ? audio.headings : indexHeadings;
            if (finalHeadings.length > 0) {
                readerIndexBtn.style.display = "flex";
                readerIndexBtn.onclick = () => openIndexSheet(finalHeadings);
            } else {
                readerIndexBtn.style.display = "none";
            }
        }"""
content = content.replace(reader_target, reader_replacement)

# 3. Patch openSharedReaderMode
shared_reader_target = """        // 문장 렌더링
        sentences.forEach((s, index) => {
            const span = document.createElement("span");
            span.className = "reader-sentence";
            span.id = `sent-${index}`;
            span.textContent = s.text + " ";

            span.addEventListener("click", () => {
                readerAudio.currentTime = s.start / 1000;
                readerAudio.play().catch(function(err) { console.log("Play failed:", err); });
                showPauseIcon();
            });

            readerContent.appendChild(span);
        });"""
shared_reader_replacement = reader_replacement.replace("audio.sentences.forEach", "sentences.forEach").replace("audio.headings", "[]")
content = content.replace(shared_reader_target, shared_reader_replacement)

with open("static/app.js", "w") as f:
    f.write(content)

print("Patched app.js successfully!")
