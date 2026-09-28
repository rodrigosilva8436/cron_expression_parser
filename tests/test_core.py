import unittest
from datetime import datetime

from cron_expression_parser import CronExpression, parse


class TestParse(unittest.TestCase):
    def test_wildcard_all_fields(self):
        expr = parse("* * * * *")
        self.assertEqual(sorted(expr.minute.values), list(range(60)))
        self.assertEqual(sorted(expr.hour.values), list(range(24)))
        self.assertEqual(sorted(expr.day_of_month.values), list(range(1, 32)))
        self.assertEqual(sorted(expr.month.values), list(range(1, 13)))
        self.assertEqual(sorted(expr.day_of_week.values), list(range(7)))

    def test_single_values(self):
        expr = parse("5 4 3 2 1")
        self.assertEqual(expr.minute.values, frozenset({5}))
        self.assertEqual(expr.hour.values, frozenset({4}))
        self.assertEqual(expr.day_of_month.values, frozenset({3}))
        self.assertEqual(expr.month.values, frozenset({2}))
        self.assertEqual(expr.day_of_week.values, frozenset({1}))

    def test_list_values(self):
        expr = parse("1,2,3 0 * * *")
        self.assertEqual(expr.minute.values, frozenset({1, 2, 3}))

    def test_range_values(self):
        expr = parse("1-5 0 * * *")
        self.assertEqual(expr.minute.values, frozenset({1, 2, 3, 4, 5}))

    def test_step_with_wildcard(self):
        expr = parse("*/15 * * * *")
        self.assertEqual(expr.minute.values, frozenset({0, 15, 30, 45}))

    def test_step_with_range(self):
        expr = parse("1-10/2 * * * *")
        self.assertEqual(expr.minute.values, frozenset({1, 3, 5, 7, 9}))

    def test_step_with_single_value(self):
        expr = parse("5/10 * * * *")
        self.assertEqual(expr.minute.values, frozenset({5, 15, 25, 35, 45, 55}))

    def test_dow_seven_normalised_to_zero(self):
        expr = parse("* * * * 7")
        self.assertEqual(expr.day_of_week.values, frozenset({0}))

    def test_dow_zero_and_seven_both_sunday(self):
        expr = parse("* * * * 0,7")
        self.assertEqual(expr.day_of_week.values, frozenset({0}))

    def test_too_few_fields(self):
        with self.assertRaises(ValueError):
            parse("* * * *")

    def test_too_many_fields(self):
        with self.assertRaises(ValueError):
            parse("* * * * * *")

    def test_value_out_of_range(self):
        with self.assertRaises(ValueError):
            parse("60 * * * *")

    def test_invalid_step_zero(self):
        with self.assertRaises(ValueError):
            parse("*/0 * * * *")

    def test_range_start_exceeds_end(self):
        with self.assertRaises(ValueError):
            parse("5-1 * * * *")

    def test_non_string_input(self):
        with self.assertRaises(TypeError):
            parse(123)


class TestNextAfter(unittest.TestCase):
    def test_every_minute(self):
        expr = parse("* * * * *")
        start = datetime(2024, 1, 15, 10, 30, 45)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 10, 31, 0))

    def test_specific_minute(self):
        expr = parse("15 * * * *")
        start = datetime(2024, 1, 15, 10, 10, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 10, 15, 0))

    def test_minute_already_passed_this_hour(self):
        expr = parse("15 * * * *")
        start = datetime(2024, 1, 15, 10, 20, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 11, 15, 0))

    def test_specific_hour_and_minute(self):
        expr = parse("30 14 * * *")
        start = datetime(2024, 1, 15, 10, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 14, 30, 0))

    def test_next_day_when_hour_passed(self):
        expr = parse("0 9 * * *")
        start = datetime(2024, 1, 15, 10, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 16, 9, 0, 0))

    def test_specific_day_of_month(self):
        expr = parse("0 0 1 * *")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 2, 1, 0, 0, 0))

    def test_specific_month(self):
        expr = parse("0 0 1 6 *")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 6, 1, 0, 0, 0))

    def test_day_of_week_friday(self):
        # 2024-01-15 is a Monday.
        expr = parse("0 12 * * 5")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 19, 12, 0, 0))

    def test_day_of_week_sunday_as_zero(self):
        # 2024-01-15 is a Monday; next Sunday is 2024-01-21.
        expr = parse("0 0 * * 0")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 21, 0, 0, 0))

    def test_day_of_week_sunday_as_seven(self):
        expr = parse("0 0 * * 7")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 21, 0, 0, 0))

    def test_dom_and_dow_both_restricted_or_semantics(self):
        # 2024-01-15 is Monday (cron dow=1).
        # Day 15 matches dom, Monday matches dow (1). So the 15th should fire.
        expr = parse("0 0 15 * 1")
        start = datetime(2024, 1, 14, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 0, 0, 0))

    def test_dom_and_dow_or_picks_dow_match(self):
        # dom=20, dow=5 (Friday). 2024-01-15 is Monday.
        # 2024-01-19 is Friday (dow=5) but dom=19 (no match).
        # 2024-01-20 is Saturday, dom=20 matches.
        # Friday the 19th should fire because dow matches.
        expr = parse("0 0 20 * 5")
        start = datetime(2024, 1, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 19, 0, 0, 0))

    def test_february_30th_never_matches(self):
        expr = parse("0 0 30 2 *")
        start = datetime(2024, 1, 1, 0, 0, 0)
        with self.assertRaises(ValueError):
            expr.next_after(start)

    def test_start_at_exact_fire_time_returns_next(self):
        expr = parse("0 12 * * *")
        start = datetime(2024, 1, 15, 12, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 16, 12, 0, 0))

    def test_step_every_15_minutes(self):
        expr = parse("*/15 * * * *")
        start = datetime(2024, 1, 15, 10, 7, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2024, 1, 15, 10, 15, 0))

    def test_year_boundary(self):
        expr = parse("0 0 1 1 *")
        start = datetime(2024, 6, 15, 0, 0, 0)
        result = expr.next_after(start)
        self.assertEqual(result, datetime(2025, 1, 1, 0, 0, 0))

    def test_repr_is_string(self):
        expr = parse("5 4 * * *")
        s = repr(expr)
        self.assertIsInstance(s, str)
        self.assertIn("CronExpression", s)


if __name__ == "__main__":
    unittest.main()
