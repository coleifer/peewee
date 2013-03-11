import datetime
import psycopg2
import unittest

from peewee import *
from playhouse.migrate import *


db = PostgresqlDatabase('peewee_test')

class BaseModel(Model):
    class Meta:
        database = db

class Tag(BaseModel):
    tag = CharField()


class MigrateTestCase(unittest.TestCase):
    integrity_error = psycopg2.IntegrityError

    def setUp(self):
        Tag._meta.db_table = 'tag'
        Tag.drop_table(True)
        Tag.create_table()

        self.migrator = Migrator(db)

    def test_add_column(self):
        df = DateTimeField(null=True)
        df_def = DateTimeField(default=datetime.datetime(2012, 1, 1))
        cf = CharField(max_length=200, default='')
        bf = BooleanField(default=True)
        ff = FloatField(default=0)

        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')

        with db.transaction():
            self.migrator.add_column(Tag, df, 'pub_date')
            self.migrator.add_column(Tag, df_def, 'modified_date')
            self.migrator.add_column(Tag, cf, 'comment')
            self.migrator.add_column(Tag, bf, 'is_public')
            self.migrator.add_column(Tag, ff, 'popularity')

        curs = db.execute_sql('select id, tag, pub_date, modified_date, comment, is_public, popularity from tag order by tag asc')
        rows = curs.fetchall()

        self.assertEqual(rows, [
            (t1.id, 't1', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
            (t2.id, 't2', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
        ])

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
