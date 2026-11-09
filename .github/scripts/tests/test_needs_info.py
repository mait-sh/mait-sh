"""Tests for needs_info.py, including a dry run against a fixture."""
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import needs_info as ni  # noqa: E402

NOW = ni.ts("2026-11-20T12:00:00Z")


def issue(number, author="reporter", state="open", labels=("bug", "needs-info")):
    return {"number": number, "state": state, "user": {"login": author},
            "labels": [{"name": l} for l in labels]}


def labeled(at, name="needs-info"):
    return {"event": "labeled", "label": {"name": name}, "created_at": at}


def comment(at, who):
    return {"user": {"login": who}, "created_at": at, "body": "..."}


class Decide(unittest.TestCase):
    def test_closes_after_seven_days_without_reply(self):
        verdict, _ = ni.decide(issue(1), [labeled("2026-11-13T12:00:00Z")], [], NOW)
        self.assertEqual(verdict, "close")

    def test_waits_before_seven_days(self):
        verdict, _ = ni.decide(issue(1), [labeled("2026-11-13T12:00:01Z")], [], NOW)
        self.assertEqual(verdict, "wait")

    def test_author_reply_after_label_keeps_it_open(self):
        verdict, _ = ni.decide(issue(1), [labeled("2026-11-01T00:00:00Z")],
                               [comment("2026-11-02T00:00:00Z", "reporter")], NOW)
        self.assertEqual(verdict, "replied")

    def test_reply_before_label_or_by_someone_else_does_not_count(self):
        verdict, _ = ni.decide(issue(1), [labeled("2026-11-05T00:00:00Z")],
                               [comment("2026-11-04T00:00:00Z", "reporter"),
                                comment("2026-11-06T00:00:00Z", "maintainer")], NOW)
        self.assertEqual(verdict, "close")

    def test_relabel_restarts_the_clock(self):
        events = [labeled("2026-11-01T00:00:00Z"),
                  {"event": "unlabeled", "label": {"name": "needs-info"}, "created_at": "2026-11-02T00:00:00Z"},
                  labeled("2026-11-18T00:00:00Z")]
        verdict, _ = ni.decide(issue(1), events, [comment("2026-11-03T00:00:00Z", "reporter")], NOW)
        self.assertEqual(verdict, "wait")

    def test_other_labels_and_missing_events_are_skipped(self):
        self.assertEqual(ni.decide(issue(1), [labeled("2026-11-01T00:00:00Z", "bug")], [], NOW)[0], "skip")
        self.assertEqual(ni.decide(issue(1, labels=("bug",)), [labeled("2026-11-01T00:00:00Z")], [], NOW)[0], "skip")
        self.assertEqual(ni.decide(issue(1, state="closed"), [labeled("2026-11-01T00:00:00Z")], [], NOW)[0], "skip")
        pr = dict(issue(1), pull_request={})
        self.assertEqual(ni.decide(pr, [labeled("2026-11-01T00:00:00Z")], [], NOW)[0], "skip")


class DecideReply(unittest.TestCase):
    def test_author_reply_on_open_issue(self):
        self.assertEqual(ni.decide_reply(issue(1), comment("2026-11-20T00:00:00Z", "reporter"), None),
                         [("remove_label", "needs-info"), ("add_label", "needs-triage")])

    def test_author_reply_reopens_issue_closed_by_the_bot(self):
        writes = ni.decide_reply(issue(1, state="closed"), comment("x", "reporter"), ni.BOT)
        self.assertIn(("reopen", None), writes)

    def test_issue_closed_by_a_person_is_not_reopened(self):
        writes = ni.decide_reply(issue(1, state="closed"), comment("x", "reporter"), "maintainer")
        self.assertNotIn(("reopen", None), writes)

    def test_other_commenters_and_unlabelled_issues_do_nothing(self):
        self.assertEqual(ni.decide_reply(issue(1), comment("x", "someone"), None), [])
        self.assertEqual(ni.decide_reply(issue(1, labels=("bug",)), comment("x", "reporter"), None), [])


class DryRun(unittest.TestCase):
    """Runs the command line end to end against fake data; no API calls."""

    FIXTURE = {
        "issues": [
            issue(10),                                  # stale: close
            issue(11),                                  # author replied: keep
            issue(12),                                  # too recent: wait
            issue(13, labels=("question",)),            # not labelled: ignored
            issue(14, state="closed"),                  # closed: ignored
        ],
        "events": {
            "10": [labeled("2026-11-10T00:00:00Z")],
            "11": [labeled("2026-11-10T00:00:00Z")],
            "12": [labeled("2026-11-19T00:00:00Z")],
        },
        "comments": {
            "10": [comment("2026-11-11T00:00:00Z", "maintainer")],
            "11": [comment("2026-11-12T00:00:00Z", "reporter")],
        },
        "closed_by": {"14": ni.BOT},
    }

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.fixture = os.path.join(self.dir.name, "fixture.json")
        with open(self.fixture, "w") as fh:
            json.dump(self.FIXTURE, fh)

    def tearDown(self):
        self.dir.cleanup()

    def test_sweep(self):
        gh = ni.Fixture(self.fixture)
        out = io.StringIO()
        with redirect_stdout(out):
            closed = ni.sweep(gh, NOW)
        self.assertEqual(closed, 1)
        self.assertEqual([(n, a) for n, a, _ in gh.writes], [(10, "comment"), (10, "close")])
        self.assertIn("<!-- mait:needs-info-close -->", gh.writes[0][2])
        self.assertIn("#11 replied", out.getvalue())
        self.assertIn("#12 wait", out.getvalue())

    def test_reply_cli_reopens(self):
        event = {"issue": issue(14, state="closed"), "comment": comment("2026-11-21T00:00:00Z", "reporter")}
        path = os.path.join(self.dir.name, "event.json")
        with open(path, "w") as fh:
            json.dump(event, fh)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ni.main(["needs_info.py", "reply", path, "--fixture", self.fixture]), 0)
        self.assertIn("[dry-run] #14 reopen", out.getvalue())
        self.assertIn("[dry-run] #14 remove_label needs-info", out.getvalue())

    def test_sweep_cli_with_now(self):
        out = io.StringIO()
        with redirect_stdout(out):
            ni.main(["needs_info.py", "sweep", "--fixture", self.fixture, "--now", "2026-11-30T00:00:00Z"])
        text = out.getvalue()
        self.assertIn("[dry-run] #10 close", text)
        self.assertIn("[dry-run] #12 close", text)
        self.assertNotIn("#11 close", text)


if __name__ == "__main__":
    unittest.main()
