from peewee import *
from playhouse.db_url import connect, parse
from playhouse.sqlite_ext import SqliteExtDatabase
from playhouse.tests.base import PeeweeTestCase


class TestDBURL(PeeweeTestCase):
    def test_db_url_parse(self):
        cfg = parse('mysql://usr:pwd@hst:123/db')
        self.assertEqual(cfg['user'], 'usr')
        self.assertEqual(cfg['passwd'], 'pwd')
        self.assertEqual(cfg['host'], 'hst')
        self.assertEqual(cfg['database'], 'db')
        self.assertEqual(cfg['port'], 123)
        cfg = parse('postgresql://usr:pwd@hst/db')
        self.assertEqual(cfg['password'], 'pwd')

    def test_db_url(self):
        db = connect('sqlite:///:memory:')
        self.assertTrue(isinstance(db, SqliteDatabase))
        self.assertEqual(db.database, ':memory:')

        db = connect('sqliteext:///foo/bar.db')
        self.assertTrue(isinstance(db, SqliteExtDatabase))
        self.assertEqual(db.database, 'foo/bar.db')

        db = connect('sqlite:////this/is/absolute.path')
        self.assertEqual(db.database, '/this/is/absolute.path')

        db = connect('sqlite://')
        self.assertTrue(isinstance(db, SqliteDatabase))
        self.assertEqual(db.database, ':memory:')

    def test_bad_scheme(self):
        def _test_scheme():
            connect('missing:///')

        self.assertRaises(RuntimeError, _test_scheme)
