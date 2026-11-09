#!/usr/bin/env python3
"""Create or update the repository labels from .github/labels.yml.

Labels that exist in the repository but not in the file are left alone and
listed, unless --prune is given. --dry-run prints what would change.

Usage: sync_labels.py LABELS_FILE [--dry-run] [--prune]
Needs: the gh CLI, GH_TOKEN and GITHUB_REPOSITORY.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse

ITEM_KEYS = ("name", "color", "description")


def parse_labels(text):
    """Parse the flat labels.yml format without a YAML library.

    Accepts "- name: x" items followed by indented "key: value" lines;
    values may be double- or single-quoted. Anything else is an error.
    """
    labels = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^(- |  )(\w+):\s*(.*)$", line)
        if not match:
            raise ValueError("line %d: cannot parse %r" % (number, raw))
        lead, key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key not in ITEM_KEYS:
            raise ValueError("line %d: unknown key %r" % (number, key))
        if lead == "- ":
            labels.append({})
        elif not labels:
            raise ValueError("line %d: key outside an item" % number)
        if key in labels[-1]:
            raise ValueError("line %d: duplicate key %r" % (number, key))
        labels[-1][key] = value
    names = set()
    for label in labels:
        missing = [k for k in ITEM_KEYS if k not in label]
        if missing:
            raise ValueError("label %r misses %s" % (label.get("name"), missing))
        if not re.fullmatch(r"[0-9a-fA-F]{6}", label["color"]):
            raise ValueError("label %r: bad color %r" % (label["name"], label["color"]))
        if len(label["description"]) > 100:
            raise ValueError("label %r: description over 100 characters" % label["name"])
        if label["name"].lower() in names:
            raise ValueError("duplicate label %r" % label["name"])
        names.add(label["name"].lower())
    return labels


def plan(wanted, existing):
    """Return a list of (action, name, fields) to make existing match wanted."""
    by_name = {e["name"].lower(): e for e in existing}
    actions = []
    for label in wanted:
        current = by_name.get(label["name"].lower())
        if current is None:
            actions.append(("create", label["name"], label))
        elif (current["name"] != label["name"]
              or current["color"].lower() != label["color"].lower()
              or (current.get("description") or "") != label["description"]):
            actions.append(("update", current["name"], label))
    wanted_names = {w["name"].lower() for w in wanted}
    for current in existing:
        if current["name"].lower() not in wanted_names:
            actions.append(("extra", current["name"], None))
    return actions


def gh(args, payload=None):
    result = subprocess.run(
        ["gh", "api"] + args + (["--input", "-"] if payload is not None else []),
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def list_labels(repo):
    labels, page = [], 1
    while True:
        batch = gh(["repos/%s/labels?per_page=100&page=%d" % (repo, page)])
        labels.extend(batch)
        if len(batch) < 100:
            return labels
        page += 1


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    dry_run = "--dry-run" in argv
    prune = "--prune" in argv
    repo = os.environ["GITHUB_REPOSITORY"]
    with open(argv[1], encoding="utf-8") as fh:
        wanted = parse_labels(fh.read())
    for action, name, label in plan(wanted, list_labels(repo)):
        path = "repos/%s/labels" % repo
        quoted = urllib.parse.quote(name, safe="")
        if action == "extra" and not prune:
            print("keep (not in file): %s" % name)
            continue
        print("%s%s: %s" % ("[dry-run] " if dry_run else "", action if action != "extra" else "delete", name))
        if dry_run:
            continue
        if action == "create":
            gh([path, "--method", "POST"], label)
        elif action == "update":
            gh(["%s/%s" % (path, quoted), "--method", "PATCH"],
               {"new_name": label["name"], "color": label["color"], "description": label["description"]})
        else:
            gh(["%s/%s" % (path, quoted), "--method", "DELETE"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
