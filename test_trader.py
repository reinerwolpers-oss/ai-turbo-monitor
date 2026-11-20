"""Regression tests for the daily close used by the signal scanner."""

from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import patch

import numpy as np
import pandas as pd

import trader


class DailyCloseTests(TestCase):
    session = date(2026, 11, 19)

    def setUp(self):
        index = pd.bdate_range(end=self.session, periods=70, tz='America/New_York')
        self.data = pd.DataFrame({'Close': np.linspace(100, 50, len(index))}, index=index)

    def scan(self, data):
        with patch.object(trader.yf, 'Ticker') as ticker:
            ticker.return_value.history.return_value = data
            return trader.calculate('TTWO', self.session)

    def test_ignores_future_rows_and_uses_expected_close(self):
        baseline = self.scan(self.data)
        future = pd.DataFrame(
            {'Close': [np.nan, 999]},
            index=pd.bdate_range(start='2026-11-20', periods=2, tz='America/New_York'),
        )

        self.assertEqual(self.scan(pd.concat([self.data, future])), baseline)
        self.assertEqual(baseline['last_data_date'], '2026-11-19')
        self.assertEqual(baseline['last_close_usd'], 50.0)
        self.assertIn('schwacher Trend', baseline['signal'])

    def test_does_not_fall_back_to_yesterday_for_invalid_expected_close(self):
        for invalid in [np.nan, np.inf, 0, -1]:
            with self.subTest(invalid=invalid):
                data = self.data.copy()
                data.iloc[-1, 0] = invalid
                with self.assertRaisesRegex(ValueError, 'Ungültiger Schlusskurs am 2026-11-19'):
                    self.scan(data)

    def test_reports_stale_history(self):
        with self.assertRaisesRegex(ValueError, '2026-11-19 fehlt.*2026-11-18'):
            self.scan(self.data.iloc[:-1])

    def test_skips_invalid_older_values(self):
        data = self.data.astype(object)
        data.iloc[10:13, 0] = ['fehlt', np.inf, -1]
        self.assertEqual(self.scan(data), self.scan(self.data.drop(self.data.index[10:13])))

    def test_checks_minimum_after_cleaning(self):
        data = self.data.copy()
        data.iloc[:11, 0] = np.nan
        with self.assertRaisesRegex(ValueError, '59 von mindestens 60'):
            self.scan(data)

    def test_reports_missing_close_column(self):
        with self.assertRaisesRegex(ValueError, 'Keine historischen Schlusskurse'):
            self.scan(self.data.rename(columns={'Close': 'Open'}))


class SessionTests(TestCase):
    def test_only_runs_after_the_scheduled_close(self):
        # A session with an early close at 13:00 New York time.
        close = pd.Timestamp('2026-11-27T18:00:00Z')
        with (
            patch.object(trader, 'datetime') as clock,
            patch.object(trader.mcal, 'get_calendar') as calendar,
            patch('builtins.print'),
        ):
            schedule = calendar.return_value.schedule
            schedule.return_value = pd.DataFrame({'market_close': [close]})
            clock.now.return_value = datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc)
            self.assertIsNone(trader.completed_session_today())

            clock.now.return_value = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
            self.assertEqual(trader.completed_session_today(), date(2026, 11, 27))
            schedule.assert_called_with(start_date=date(2026, 11, 27), end_date=date(2026, 11, 27))

            schedule.return_value = pd.DataFrame()
            self.assertIsNone(trader.completed_session_today())
