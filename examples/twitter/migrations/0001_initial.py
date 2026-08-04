# Generated from a schema diff on 2026-08-04 11:04.
from peewee import *

def up(migrator, db):
    class User(Model):
        username = CharField(unique=True)
        password = CharField()
        email = CharField()
        join_date = DateTimeField()
        class Meta:
            database = db
            table_name = 'user'
    db.create_tables([User])

    class Message(Model):
        user = ForeignKeyField(User)
        content = TextField()
        pub_date = DateTimeField()
        class Meta:
            database = db
            table_name = 'message'
    db.create_tables([Message])

    class Relationship(Model):
        from_user = ForeignKeyField(User)
        to_user = ForeignKeyField(User)
        class Meta:
            database = db
            table_name = 'relationship'
            indexes = ((('from_user', 'to_user'), True),)
    db.create_tables([Relationship])


def down(migrator, db):
    migrator.migrate(migrator.drop_table('relationship'))
    migrator.migrate(migrator.drop_table('message'))
    migrator.migrate(migrator.drop_table('user'))
