"""Tests for sync_labels.py."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sync_labels  # noqa: E402

LABELS_FILE = os.path.join(HERE, "..", "..", "labels.yml")


class Parse(unittest.TestCase):
    def test_file_parses_and_matches_yaml(self):
        with open(LABELS_FILE, encoding="utf-8") as fh:
            text = fh.read()
        parsed = sync_labels.parse_labels(text)
        self.assertEqual(len(parsed), 21)
        try:
            import yaml
        except ImportError:
            return
        self.assertEqual(parsed, yaml.safe_load(text))

    def test_rejects_bad_input(self):
        for text in (
            '- name: a\n  color: "zzzzzz"\n  description: x\n',
            '- name: a\n  color: "ffffff"\n',
            '- name: a\n  colour: "ffffff"\n  description: x\n',
            '- name: a\n  color: "ffffff"\n  description: x\n- name: A\n  color: "ffffff"\n  description: y\n',
            '  color: "ffffff"\n',
            'name: a\n',
        ):
            with self.assertRaises(ValueError, msg=text):
                sync_labels.parse_labels(text)


class Plan(unittest.TestCase):
    def test_plan(self):
        wanted = [
            {"name": "bug", "color": "d73a4a", "description": "Something does not work"},
            {"name": "needs-info", "color": "fbca04", "description": "Waiting"},
            {"name": "question", "color": "d876e3", "description": "A question"},
        ]
        existing = [
            {"name": "bug", "color": "D73A4A", "description": "Something isn't working"},
            {"name": "question", "color": "d876e3", "description": "A question"},
            {"name": "good first issue", "color": "7057ff", "description": "Good for newcomers"},
        ]
        self.assertEqual(sync_labels.plan(wanted, existing), [
            ("update", "bug", wanted[0]),
            ("create", "needs-info", wanted[1]),
            ("extra", "good first issue", None),
        ])


if __name__ == "__main__":
    unittest.main()
