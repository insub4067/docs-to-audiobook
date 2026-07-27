with open("static/app.js", "r") as f:
    content = f.read()

target1 = """            } else {
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
            }"""

replacement1 = """            } else {
                const mdHeadingMatch = rawText.match(/^(#{1,3})\\s+(.+)$/);
                if (mdHeadingMatch) {
                    isHeading = true;
                    level = mdHeadingMatch[1].length;
                    titleText = cleanDisplayText(mdHeadingMatch[2]);
                }
            }"""

if target1 in content:
    content = content.replace(target1, replacement1)
    with open("static/app.js", "w") as f:
        f.write(content)
    print("Patched app.js successfully using string replace!")
else:
    print("Target not found with string replace!")
    print("Finding it line by line...")
    import sys
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "const mdHeadingMatch = rawText.match(/^(#{1,3})\\s+(.+)$/);" in line:
            print(f"Found at line {i+1}")
            start_idx = i - 1 # "} else {"
            end_idx = i + 17 # "}"
            print("To be replaced:")
            print("\n".join(lines[start_idx:end_idx+1]))
            
            new_lines = lines[:start_idx] + replacement1.split('\n') + lines[end_idx+1:]
            with open("static/app.js", "w") as f:
                f.write("\n".join(new_lines))
            print("Patched app.js with line-by-line replace!")
            sys.exit(0)
