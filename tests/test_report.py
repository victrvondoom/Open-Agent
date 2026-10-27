"""Generated docs: deck/README numbers must equal a fresh investigation and benchmark run."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from payproof.bench import run
from payproof.report import deck_data, write_generated_docs
from payproof.sources import LocalFixtureSource, load_plans
from payproof.workflow import investigate

ROOT = Path(__file__).resolve().parent.parent


class ReportTests(unittest.TestCase):
    def test_generated_blocks_match_live_output(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "docs").mkdir()
        shutil.copy(ROOT / "docs" / "deck.html", tmp / "docs" / "deck.html")
        shutil.copy(ROOT / "README.md", tmp / "README.md")
        report = run(["CASE-1001", "CASE-1015"], write=False)
        write_generated_docs(report, root=tmp)
        deck = (tmp / "docs" / "deck.html").read_text(encoding="utf-8")
        data = json.loads(re.search(r'<script id="deck-data" type="application/json">(.*?)</script>', deck, re.S).group(1))
        live = investigate(LocalFixtureSource(user_dir=None).load_case("CASE-1001"), load_plans())
        self.assertEqual(data["demo"]["delta"], live["calculation"]["delta"])
        self.assertEqual(data["agent"]["cases"], 2)
        readme = (tmp / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"| **Verified commission due** | ${float(live['calculation']['due']):,.2f}", readme)
        # idempotent: regenerating does not duplicate blocks
        write_generated_docs(report, root=tmp)
        self.assertEqual((tmp / "README.md").read_text(encoding="utf-8").count("<!-- BENCH:START -->"), 1)
        self.assertEqual(deck_data(report)["demo"]["case_id"], "CASE-1001")


if __name__ == "__main__":
    unittest.main()
