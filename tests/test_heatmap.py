import os
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi import HTTPException
from upload import heatmap_data


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def scalars(self, query):
        return [datetime(2026, 11, 1, 5, 15, tzinfo=timezone.utc),
                datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc),
                datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)]


class HeatmapTests(unittest.IsolatedAsyncioTestCase):
    async def test_bucket_sizes_and_repeated_hour(self):
        with patch("upload.SessionLocal", FakeSession):
            for size, expected in [(15, {5: 2, 6: 1}), (30, {2: 2, 3: 1}), (60, {1: 3})]:
                with self.subTest(size=size):
                    data = await heatmap_data(date(2026, 11, 1), "America/New_York", size)
                    self.assertEqual(len(data["counts"][6]), 1440 // size)
                    self.assertEqual(data["bucket_minutes"], size)
                    self.assertEqual(data["total"], 3)
                    self.assertEqual({i: n for i, n in enumerate(data["counts"][6]) if n}, expected)

    async def test_invalid_bucket_size(self):
        with self.assertRaises(HTTPException) as exc:
            await heatmap_data(date(2026, 11, 1), "UTC", 20)
        self.assertEqual(exc.exception.status_code, 400)

    async def test_csv_export_uses_week_and_local_timestamps(self):
        import csv
        import io
        from upload import weekly_taps_csv

        class ExportSession(FakeSession):
            async def execute(self, query):
                params = list(query.compile().params.values())
                assert params == [datetime(2026, 10, 26, 4, tzinfo=timezone.utc),
                                  datetime(2026, 11, 2, 5, tzinfo=timezone.utc)]
                return [(datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc),
                         "tag", "Alex", "Alex, Example", "reader", True)]

        with patch("upload.SessionLocal", ExportSession):
            response = await weekly_taps_csv(date(2026, 11, 1), "America/New_York")
        rows = list(csv.DictReader(io.StringIO(response.body.decode())))
        self.assertEqual(rows[0]["tapped_at"], "2026-11-01T01:15:00-05:00")
        self.assertEqual(rows[0]["full_name"], "Alex, Example")
        self.assertEqual(rows[0]["direction"], "in")
        self.assertIn("taps-2026-10-26.csv", response.headers["content-disposition"])
