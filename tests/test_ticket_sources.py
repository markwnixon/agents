import unittest

from ticket_sources import ordered_ticket_sources


class OrderedTicketSourcesTests(unittest.TestCase):
    def test_preserves_out_then_in_order(self):
        self.assertEqual(
            ordered_ticket_sources("CONT_OUT.pdf", "CONT_IN.pdf"),
            ("CONT_OUT.pdf", "CONT_IN.pdf"),
        )

    def test_reorders_in_then_out(self):
        self.assertEqual(
            ordered_ticket_sources("CONT_IN.pdf", "CONT_OUT.pdf"),
            ("CONT_OUT.pdf", "CONT_IN.pdf"),
        )

    def test_first_source_may_be_none(self):
        self.assertEqual(ordered_ticket_sources(None, "CONT_IN.pdf"), ("", "CONT_IN.pdf"))

    def test_second_source_may_be_none(self):
        self.assertEqual(ordered_ticket_sources("CONT_OUT.pdf", None), ("CONT_OUT.pdf", ""))


if __name__ == "__main__":
    unittest.main()
