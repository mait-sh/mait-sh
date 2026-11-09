#!/usr/bin/env python3
"""Map the answers of an issue form to area, platform and severity labels.

GitHub renders an issue form as Markdown: one "### <field label>" heading per
field, a blank line, then the answer ("_No response_" when it was left empty).
This script reads that body and prints one label per line.

Usage: issue_form_labels.py EVENT_JSON   (the issues event, $GITHUB_EVENT_PATH)
       issue_form_labels.py --body FILE  (a raw issue body, for testing)
"""
import json
import re
import sys

# Field label in the form -> {dropdown option text -> label}. Keep these in
# sync with .github/ISSUE_TEMPLATE/*.yml and .github/labels.yml.
AREA = {
    "aidcx launcher and project containers": "aidcx",
    "Agent tools (MCP servers)": "mcp",
    "Desktop and graphical sessions": "desktop",
    "Documentation": "docs",
    "Portal (mait.sh, account, sign-in)": "portal",
}
PLATFORM = {
    "Linux": "linux",
    "Mac, inside aidcx terminal": "mac",
    "Windows, inside aidcx terminal": "windows",
}
SEVERITY = {
    "Blocks use (I cannot continue)": "sev-blocker",
    "Workaround exists": "sev-major",
    "Cosmetic": "sev-minor",
}
FIELDS = {
    "MAIT component": AREA,
    "Where did you run this?": PLATFORM,
    "How bad is it?": SEVERITY,
}

HEADING = re.compile(r"^###\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def parse_sections(body):
    """Return {heading: answer text} for top-level "### " headings.

    Headings inside fenced code blocks are ignored, and the first occurrence
    of a heading wins, because GitHub renders form fields in order.
    """
    sections = {}
    current = None
    lines = []
    in_fence = False
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING.match(line)
        if match:
            if current is not None and current not in sections:
                sections[current] = "\n".join(lines).strip()
            current = match.group(1)
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None and current not in sections:
        sections[current] = "\n".join(lines).strip()
    return sections


def labels_for(body):
    sections = parse_sections(body)
    labels = []
    for field, mapping in FIELDS.items():
        answer = sections.get(field)
        if answer is None or answer == "_No response_":
            continue
        label = mapping.get(answer)
        if label and label not in labels:
            labels.append(label)
    return labels


def main(argv):
    if len(argv) == 3 and argv[1] == "--body":
        with open(argv[2], encoding="utf-8") as fh:
            body = fh.read()
    elif len(argv) == 2:
        with open(argv[1], encoding="utf-8") as fh:
            event = json.load(fh)
        body = (event.get("issue") or {}).get("body") or ""
    else:
        sys.stderr.write(__doc__)
        return 2
    for label in labels_for(body):
        print(label)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
