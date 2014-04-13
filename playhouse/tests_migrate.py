import datetime
import unittest

from peewee import *
from playhouse.migrate import *

import logging
logger = logging.getLogger('peewee')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


try:
    import psycopg2
    pg_db = PostgresqlDatabase('peewee_test')
except ImportError:
    pg_db = None

sqlite_db = SqliteDatabase(':memory:')

class Tag(Model):
    tag = CharField()


class BaseMigrationTestCase(object):
    database = None
    migrator_class = None

    def setUp(self):
        Tag._meta.database = self.database
        Tag.drop_table(True)
        Tag.create_table()

        self.migrator = self.migrator_class(self.database)

    def test_add_column(self):
        df = DateTimeField(null=True)
        df_def = DateTimeField(default=datetime.datetime(2012, 1, 1))
        cf = CharField(max_length=200, default='')
        bf = BooleanField(default=True)
        ff = FloatField(default=0)

        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')

        def add_column(field_name, field_obj):
            return self.migrator.add_column('tag', field_name, field_obj)
        add_pub_date = add_column('pub_date', df)
        add_modified_date = add_column('modified_date', df_def)
        add_comment = add_column('comment', cf)
        add_is_public = add_column('is_public', bf)
        add_popularity = add_column('popularity', ff)

        migrate(
            self.migrator,
            add_pub_date,
            add_modified_date,
            add_comment,
            add_is_public,
            add_popularity,
        )

        query = """
            SELECT id, tag, pub_date, modified_date, comment, is_public, popularity
            FROM tag
            ORDER BY tag ASC
        """
        curs = self.database.execute_sql(query)
        rows = curs.fetchall()

        self.assertEqual(rows, [
            (t1.id, 't1', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
            (t2.id, 't2', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
        ])


#class PostgresqlMigrationTestCase(BaseMigrationTestCase, unittest.TestCase):
#    database = pg_db
#    migrator_class = PostgresqlMigrator


class SqliteMigrationTestCase(BaseMigrationTestCase, unittest.TestCase):
    database = sqlite_db
    migrator_class = SqliteMigrator


    """
    def test_rename_column(self):
        t1 = Tag.create(tag='t1')

        with db.transaction():
            self.migrator.rename_column(Tag, 'tag', 'foo')

        curs = db.execute_sql('select foo from tag')
        rows = curs.fetchall()

        self.assertEqual(rows, [
            ('t1',),
        ])

    def test_drop_column(self):
        t1 = Tag.create(tag='t1')

        with db.transaction():
            self.migrator.drop_column(Tag, 'tag')

        curs = db.execute_sql('select * from tag')
        rows = curs.fetchall()

        self.assertEqual(rows, [
            (t1.id,),
        ])

    def test_set_nullable(self):
        t1 = Tag.create(tag='t1')

        with db.transaction():
            self.migrator.set_nullable(Tag, Tag.tag, True)

        t2 = Tag.create(tag=None)
        tags = [t.tag for t in Tag.select().order_by(Tag.id)]
        self.assertEqual(tags, ['t1', None])

        t2.delete_instance()

        with db.transaction():
            self.migrator.set_nullable(Tag, Tag.tag, False)

        with db.transaction():
            self.assertRaises(self.integrity_error, Tag.create, tag=None)

    def test_rename_table(self):
        t1 = Tag.create(tag='t1')

        self.migrator.rename_table(Tag, 'tagzz')
        curs = db.execute_sql('select * from tagzz')
        res = curs.fetchall()

        self.assertEqual(res, [
            (t1.id, 't1'),
        ])

        self.migrator.rename_table(Tag, 'tag')
    """
