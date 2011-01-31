import peewee


test_db = peewee.Database(peewee.SqliteAdapter(), 'test_pw.db')

class User(peewee.Model):
    username = peewee.CharField()
    active = peewee.BooleanField()

    class Meta:
        database = test_db


class Blog(peewee.Model):
    user = peewee.ForeignKeyField(User)
    name = peewee.CharField()

    class Meta:
        database = test_db


class Entry(peewee.Model):
    blog = peewee.ForeignKeyField(Blog)
    title = peewee.CharField()
    content = peewee.TextField()
    pub_date = peewee.DateTimeField()

    class Meta:
        database = test_db


def create_tables():
    test_db.connect()
    User.create_table()
    Blog.create_table()
    Entry.create_table()


def drop_tables():
    test_db.connect()
    Entry.drop_table(fail_silently=True)
    Blog.drop_table(fail_silently=True)
    User.drop_table(fail_silently=True)
