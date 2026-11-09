#!/usr/bin/env python3
"""Close issues that wait for information too long, and reopen them on reply.

  needs_info.py sweep [--dry-run] [--fixture FILE] [--now ISO8601]
      For every open issue labelled needs-info: if its author has not
      commented since the label was last added and the label is at least
      DAYS days old, comment and close the issue as not planned.

  needs_info.py reply EVENT_JSON [--dry-run] [--fixture FILE]
      For an issue_comment event: if the issue author commented on an issue
      labelled needs-info, remove needs-info, add needs-triage, and reopen
      the issue if this automation closed it.

--fixture reads issues, events and comments from a JSON file instead of the
GitHub API (for tests); --dry-run prints the writes instead of making them.
Needs: the gh CLI, GH_TOKEN and GITHUB_REPOSITORY (not with --fixture).
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.parse

LABEL = "needs-info"
TRIAGE = "needs-triage"
DAYS = 7
BOT = "github-actions[bot]"
CLOSE_COMMENT = (
    "We asked for more information %d days ago and have not heard back, so we "
    "are closing this issue for now.\n\n"
    "If you opened this issue, reply here with the details and it reopens "
    "automatically. Thank you for the report.\n\n"
    "The MAIT Team\n\n"
    "<!-- mait:needs-info-close -->" % DAYS
)


def ts(value):
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


def has_label(issue, name):
    return any(l["name"] == name for l in issue.get("labels", []))


def label_added_at(events):
    """Time the needs-info label was last added, or None."""
    times = [ts(e["created_at"]) for e in events
             if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == LABEL]
    return max(times) if times else None


def decide(issue, events, comments, now, days=DAYS):
    """Return ("close" | "wait" | "replied" | "skip", reason)."""
    if issue.get("state") != "open" or "pull_request" in issue:
        return "skip", "not an open issue"
    if not has_label(issue, LABEL):
        return "skip", "no %s label" % LABEL
    added = label_added_at(events)
    if added is None:
        return "skip", "cannot tell when %s was added" % LABEL
    author = issue["user"]["login"]
    replies = [c for c in comments
               if c["user"]["login"] == author and ts(c["created_at"]) > added]
    if replies:
        return "replied", "author replied at %s" % replies[-1]["created_at"]
    age = now - added
    if age >= datetime.timedelta(days=days):
        return "close", "label added %s, %d days without a reply" % (added.isoformat(), age.days)
    return "wait", "label added %s, %d days ago" % (added.isoformat(), age.days)


def decide_reply(issue, comment, closed_by):
    """Return the list of writes for a new comment on an issue."""
    if "pull_request" in issue or not has_label(issue, LABEL):
        return []
    if comment["user"]["login"] != issue["user"]["login"]:
        return []
    writes = [("remove_label", LABEL), ("add_label", TRIAGE)]
    if issue.get("state") == "closed" and closed_by == BOT:
        writes.append(("reopen", None))
    return writes


class GitHub:
    def __init__(self, repo, dry_run):
        self.repo, self.dry_run = repo, dry_run

    def _api(self, args, payload=None):
        cmd = ["gh", "api"] + args + (["--input", "-"] if payload is not None else [])
        out = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out) if out.strip() else None

    def _pages(self, path):
        items, page = [], 1
        sep = "&" if "?" in path else "?"
        while True:
            batch = self._api(["%s%sper_page=100&page=%d" % (path, sep, page)])
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def open_issues(self):
        return self._pages("repos/%s/issues?state=open&labels=%s" % (self.repo, LABEL))

    def events(self, number):
        return self._pages("repos/%s/issues/%d/events" % (self.repo, number))

    def comments(self, number):
        return self._pages("repos/%s/issues/%d/comments" % (self.repo, number))

    def closed_by(self, number):
        issue = self._api(["repos/%s/issues/%d" % (self.repo, number)])
        return (issue.get("closed_by") or {}).get("login")

    def write(self, number, action, arg=None):
        if self.dry_run:
            print("  [dry-run] #%d %s %s" % (number, action, arg or ""))
            return
        base = "repos/%s/issues/%d" % (self.repo, number)
        if action == "comment":
            self._api([base + "/comments", "--method", "POST"], {"body": arg})
        elif action == "close":
            self._api([base, "--method", "PATCH"], {"state": "closed", "state_reason": "not_planned"})
        elif action == "reopen":
            self._api([base, "--method", "PATCH"], {"state": "open"})
        elif action == "add_label":
            self._api([base + "/labels", "--method", "POST"], {"labels": [arg]})
        elif action == "remove_label":
            try:
                self._api([base + "/labels/" + urllib.parse.quote(arg, safe=""), "--method", "DELETE"])
            except subprocess.CalledProcessError:
                pass  # already removed
        print("  #%d %s %s" % (number, action, arg or ""))


class Fixture(GitHub):
    """Reads a JSON fixture; writes are recorded in self.writes, never sent."""

    def __init__(self, path):
        super().__init__("fixture/repo", True)
        with open(path, encoding="utf-8") as fh:
            self.data = json.load(fh)
        self.writes = []

    def open_issues(self):
        return [i for i in self.data["issues"]
                if i.get("state") == "open" and has_label(i, LABEL)]

    def events(self, number):
        return self.data.get("events", {}).get(str(number), [])

    def comments(self, number):
        return self.data.get("comments", {}).get(str(number), [])

    def closed_by(self, number):
        return self.data.get("closed_by", {}).get(str(number))

    def write(self, number, action, arg=None):
        self.writes.append((number, action, arg))
        super().write(number, action, arg)


def sweep(gh, now):
    closed = 0
    for issue in gh.open_issues():
        number = issue["number"]
        verdict, reason = decide(issue, gh.events(number), gh.comments(number), now)
        print("#%d %s: %s" % (number, verdict, reason))
        if verdict == "close":
            gh.write(number, "comment", CLOSE_COMMENT)
            gh.write(number, "close")
            closed += 1
    return closed


def reply(gh, event):
    issue, comment = event["issue"], event["comment"]
    number = issue["number"]
    closed_by = gh.closed_by(number) if issue.get("state") == "closed" else None
    writes = decide_reply(issue, comment, closed_by)
    print("#%d: %s" % (number, ", ".join(w[0] for w in writes) or "nothing to do"))
    for action, arg in writes:
        gh.write(number, action, arg)
    return writes


def option(argv, name):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1]
    return None


def main(argv):
    if len(argv) < 2 or argv[1] not in ("sweep", "reply"):
        sys.stderr.write(__doc__)
        return 2
    dry_run = "--dry-run" in argv
    fixture = option(argv, "--fixture")
    gh = Fixture(fixture) if fixture else GitHub(os.environ["GITHUB_REPOSITORY"], dry_run)
    if argv[1] == "sweep":
        now_arg = option(argv, "--now")
        now = ts(now_arg) if now_arg else datetime.datetime.now(datetime.timezone.utc)
        sweep(gh, now)
    else:
        with open(argv[2], encoding="utf-8") as fh:
            reply(gh, json.load(fh))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
