# Generated from a schema diff on 2026-08-04 11:06.
from peewee import *
from playhouse.sqlite_ext import FTS5Model
from playhouse.sqlite_ext import SearchField


def up(migrator, db):
    class Entry(Model):
        title = CharField()
        slug = CharField(unique=True)
        content = TextField()
        published = BooleanField(index=True)
        timestamp = DateTimeField(index=True)
        class Meta:
            database = db
            table_name = 'entry'
    db.create_tables([Entry])

    # Added by hand - migrations do not capture virtual tables at present.
    class FTSEntry(FTS5Model):
        content = SearchField()
        class Meta:
            database = db
    db.create_tables([FTSEntry])


def down(migrator, db):
    migrator.migrate(migrator.drop_table('entry'))
    migrator.migrate(migrator.drop_table('ftsentry'))
