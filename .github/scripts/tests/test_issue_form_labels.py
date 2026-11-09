"""Tests for issue_form_labels.py. Run: python3 -m unittest discover -s .github/scripts/tests"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import issue_form_labels as ifl  # noqa: E402

TEMPLATES = os.path.join(HERE, "..", "..", "ISSUE_TEMPLATE")

# A bug report body exactly as GitHub renders the bug form.
BUG_BODY = """### What happened?

`aidcx start` stops with "readiness gate timeout".

### What did you expect to happen?

The container starts.

### Steps to reproduce

1. cd ~/project
2. aidcx start
3. wait

### Where did you run this?

Mac, inside aidcx terminal

### MAIT component

aidcx launcher and project containers

### Version

_No response_

### Diagnostics output

```text
date:   2026-11-09T10:00:00Z
### aidcx version
aidcx 1.0.0
[exit 0]
### MAIT component
Portal (mait.sh, account, sign-in)
```

### Logs and other output (optional)

_No response_

### How bad is it?

Blocks use (I cannot continue)

### Before you submit

- [X] I searched the existing issues, including closed ones.
- [X] I am on the latest release available to me.
- [X] There are no secrets, tokens, private keys or personal data in this report.
"""

ENHANCEMENT_BODY = """### What problem are you trying to solve?

I cannot find the tool list.

### Who does it affect?

Me.

### What do you do today instead?

_No response_

### Ideas for a solution (optional)

_No response_

### MAIT component

Agent tools (MCP servers)

### How important is this to you?

Nice to have
"""

QUESTION_EMPTY = """### Your question

How do I share my Git sign-in?

### MAIT component

_No response_
"""


class LabelsFor(unittest.TestCase):
    def test_bug_form(self):
        self.assertEqual(ifl.labels_for(BUG_BODY), ["aidcx", "mac", "sev-blocker"])

    def test_crlf_body(self):
        self.assertEqual(ifl.labels_for(BUG_BODY.replace("\n", "\r\n")), ["aidcx", "mac", "sev-blocker"])

    def test_enhancement_form(self):
        self.assertEqual(ifl.labels_for(ENHANCEMENT_BODY), ["mcp"])

    def test_no_response(self):
        self.assertEqual(ifl.labels_for(QUESTION_EMPTY), [])

    def test_other_and_not_applicable_add_nothing(self):
        body = BUG_BODY.replace("Mac, inside aidcx terminal", "Not on my computer (portal or docs)") \
                       .replace("aidcx launcher and project containers", "Other or not sure")
        self.assertEqual(ifl.labels_for(body), ["sev-blocker"])

    def test_each_option(self):
        for platform, label in ifl.PLATFORM.items():
            body = BUG_BODY.replace("Mac, inside aidcx terminal", platform)
            self.assertIn(label, ifl.labels_for(body))
        for option, label in ifl.AREA.items():
            body = BUG_BODY.replace("aidcx launcher and project containers", option)
            self.assertIn(label, ifl.labels_for(body))
        for option, label in ifl.SEVERITY.items():
            body = BUG_BODY.replace("Blocks use (I cannot continue)", option)
            self.assertIn(label, ifl.labels_for(body))

    def test_heading_inside_code_fence_is_ignored(self):
        # The Diagnostics block above holds a fake "### MAIT component"; only
        # the real field counts.
        self.assertNotIn("portal", ifl.labels_for(BUG_BODY))

    def test_fenced_heading_before_the_real_field_is_ignored(self):
        # A fenced block in an earlier text answer must not set a label,
        # even though it comes before the real field.
        fake = "```\n### How bad is it?\n\nCosmetic\n```\n"
        body = BUG_BODY.replace("The container starts.\n", "The container starts.\n" + fake)
        self.assertEqual(ifl.labels_for(body), ["aidcx", "mac", "sev-blocker"])

    def test_first_heading_wins(self):
        body = BUG_BODY + "\n### MAIT component\n\nDocumentation\n"
        self.assertNotIn("docs", ifl.labels_for(body))

    def test_unknown_answer_and_free_text(self):
        body = BUG_BODY.replace("Blocks use (I cannot continue)", "Blocks use (I cannot continue) please")
        self.assertNotIn("sev-blocker", ifl.labels_for(body))

    def test_empty_and_none_body(self):
        self.assertEqual(ifl.labels_for(""), [])
        self.assertEqual(ifl.labels_for(None), [])
        self.assertEqual(ifl.labels_for("Just text, no form."), [])


class MatchesForms(unittest.TestCase):
    """Every mapped option exists in the forms, and every form option is mapped or deliberately unmapped."""

    UNMAPPED = {"Other or not sure", "Not on my computer (portal or docs)"}

    def setUp(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        self.forms = {}
        for name in ("bug.yml", "enhancement.yml", "question.yml"):
            with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
                self.forms[name] = yaml.safe_load(fh)

    def test_options(self):
        seen = {}
        for name, form in self.forms.items():
            for item in form["body"]:
                label = item.get("attributes", {}).get("label")
                if item["type"] == "dropdown" and label in ifl.FIELDS:
                    options = item["attributes"]["options"]
                    seen.setdefault(label, set()).update(options)
                    for option in options:
                        self.assertTrue(option in ifl.FIELDS[label] or option in self.UNMAPPED,
                                        "%s: %r not mapped" % (name, option))
        for label, mapping in ifl.FIELDS.items():
            self.assertIn(label, seen)
            self.assertTrue(set(mapping) <= seen[label], label)

    def test_labels_exist_in_labels_file(self):
        import sync_labels
        with open(os.path.join(HERE, "..", "..", "labels.yml"), encoding="utf-8") as fh:
            names = {l["name"] for l in sync_labels.parse_labels(fh.read())}
        for mapping in ifl.FIELDS.values():
            self.assertTrue(set(mapping.values()) <= names)
        for form in self.forms.values():
            self.assertTrue(set(form["labels"]) <= names, form["labels"])


if __name__ == "__main__":
    unittest.main()
