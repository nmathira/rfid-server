import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from import_members import import_members


def user(uid, name=None, first_name=None, reference_tag=None, campus_id=None):
    return SimpleNamespace(uid=uid, name=name, first_name=first_name,
                           reference_tag=reference_tag, campus_id=campus_id)


class DB:
    def __init__(self, users):
        self.users = users
        self.committed = False

    async def execute(self, query):
        return self

    def scalars(self):
        return self.users

    async def commit(self):
        self.committed = True


class ImportTests(unittest.TestCase):
    def run_import(self, users, csv):
        db = DB(users)
        result = asyncio.run(import_members(db, csv.encode()))
        self.assertTrue(db.committed)
        return result

    def test_legacy_locations_and_repeat(self):
        a = user('a', name='ABCD')
        b = user('b', name='Old', first_name='WXYZ')
        csv = 'Jane,Doe,jane@example.com,ABCD\nJohn,Smith,john@example.com,WXYZ\n'
        result = self.run_import([a, b], csv)
        self.assertEqual(result['updated'], 2)
        self.assertEqual((a.name, a.first_name, a.reference_tag, a.campus_id),
                         ('Jane', 'Jane Doe', 'ABCD', 'jane@example.com'))
        self.assertEqual((b.name, b.first_name, b.reference_tag), ('John', 'John Smith', 'WXYZ'))
        result = self.run_import([a, b], csv)
        self.assertEqual((result['updated'], result['unchanged']), (0, 2))

    def test_issues_do_not_block_unambiguous_rows(self):
        a = user('a', first_name='ABCD')
        b = user('b', first_name='WXYZ')
        c = user('c', first_name='WXYZ')
        csv = ('Jane,Doe,jane@example.com,ABCD\nMissing,Tag,a@example.com,\n'
               'No,Match,a@example.com,QQQQ\nTwo,Users,a@example.com,WXYZ\n'
               'Bad,Email,,ABCD\nGood,Person,g@example.com,GOOD\n')
        good = user('g', name='GOOD')
        result = self.run_import([a, b, c, good], csv)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(good.name, 'Good')
        self.assertIsNone(a.reference_tag)
        self.assertEqual(len(result['issues']), 5)
        self.assertTrue(any('Multiple database' in x['reason'] for x in result['issues']))

    def test_conflicting_tags_and_names_are_safe(self):
        a = user('a', name='Alan')
        b = user('b', name='ABCD')
        csv = ('Alan,Person,a@example.com,ALAN\nOne,Person,a@example.com,ABCD\n'
               'Two,Person,b@example.com,ABCD\n')
        result = self.run_import([a, b], csv)
        self.assertEqual(result['updated'], 0)
        self.assertEqual(len(result['issues']), 3)
        self.assertEqual(a.name, 'Alan')

    def test_bad_csv_prevents_all_updates(self):
        a = user('a', name='ABCD')
        db = DB([a])
        with self.assertRaises(ValueError):
            asyncio.run(import_members(db, b'Jane,Doe,j@example.com,ABCD\n"bad'))
        self.assertFalse(db.committed)
        self.assertEqual(a.name, 'ABCD')


if __name__ == '__main__':
    unittest.main()
