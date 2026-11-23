import sys
import unittest

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
from rechts_checkliste import RECHTS_CHECKLISTE


class RechtsChecklisteTests(unittest.TestCase):
    def test_all_paths_have_required_fields(self):
        self.assertEqual(set(RECHTS_CHECKLISTE), {"1", "2", "3", "4"})
        for entry in RECHTS_CHECKLISTE.values():
            self.assertIn("titel", entry)
            self.assertIn("kurz", entry)
            self.assertIsInstance(entry["fragen"], list)
            self.assertGreater(len(entry["fragen"]), 0)
            self.assertIsInstance(entry["quellenhinweis_empfohlen"], bool)

    def test_no_clearance_claim_in_headings(self):
        combined = " ".join(str(entry["titel"] + " " + entry["kurz"])
                            for entry in RECHTS_CHECKLISTE.values())
        self.assertNotIn("rechtssicher", combined.casefold())
        self.assertNotIn("freigabe", combined.casefold())


if __name__ == "__main__":
    unittest.main()
