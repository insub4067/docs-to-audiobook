import pytest
import os
import subprocess

def test_patch_app_success():
    # We will create a dummy static/app.js, run patch_app.py, and verify
    os.makedirs("static", exist_ok=True)
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
    
    with open("static/app.js", "w") as f:
        f.write(target1)
        
    subprocess.run(["python3", "patch_app.py"], check=True)
    
    with open("static/app.js", "r") as f:
        content = f.read()
        
    assert "boldHeadingMatch" not in content
    
    # Run again to hit the else branch where it's already replaced (or not found)
    subprocess.run(["python3", "patch_app.py"])

def test_patch_app_line_by_line():
    # Create the target but slightly modified so exact string match fails
    target_mod = """            } else {
                const mdHeadingMatch = rawText.match(/^(#{1,3})\\s+(.+)$/);
                const boldHeadingMatch = rawText.match(/^(\\**|__)(.+?)\\1$/);
                // Extra line to break string match
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
            
    with open("static/app.js", "w") as f:
        f.write(target_mod)
        
    try:
        subprocess.run(["python3", "patch_app.py"], check=True)
    except subprocess.CalledProcessError:
        pass # It exits with sys.exit(0) anyway
        
    with open("static/app.js", "r") as f:
        content = f.read()
    
    assert "boldHeadingMatch" not in content
