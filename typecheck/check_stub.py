from __future__ import annotations

from collections.abc import Generator
from typing_extensions import assert_type

from peewee import (
    SQL,
    BigBitField,
    BigBitFieldData,
    CharField,
    Check,
    DatabaseProxy,
    ForeignKeyField,
    IntegerField,
    Model,
    ModelAlias,
    ModelSelect,
    NodeList,
    NoopModelSelect,
    SqliteDatabase,
    chunked,
)


class User(Model):
    username = CharField()
    age = IntegerField()
    nickname = CharField(null=True)


class Tweet(Model):
    user = ForeignKeyField(User)
    author = ForeignKeyField(User, null=True)


class Event(Model):
    flags = BigBitField()


# A field is a descriptor that resolves differently depending on whether it is
# accessed on the model class or on an instance. `Model.field` is the Field
# object itself (used to build queries), while `instance.field` is the stored
# Python value.
assert_type(User.username, CharField[str])
assert_type(User().username, str)

assert_type(User.age, IntegerField[int])
assert_type(User().age, int)

# `null=True` allows the value to include None, both in the field's own
# parameterization and in the value produced on attribute access.
assert_type(User.nickname, CharField[str | None])
assert_type(User().nickname, str | None)

# Foreign keys resolve to the related model instance, or None when nullable.
assert_type(Tweet.user, ForeignKeyField[User])
assert_type(Tweet().user, User)
assert_type(Tweet().author, User | None)

# BigBitField is a special case: the instance descriptor yields a
# BigBitFieldData wrapper rather than the underlying bytes.
assert_type(Event.flags, BigBitField)
assert_type(Event().flags, BigBitFieldData)

# __set__ accepts the field's value type...
user = User()
user.username = 'huey'
user.age = 42
user.nickname = None  # nullable field accepts None

# ...and rejects incompatible values.
user.age = 'not an int'  # type: ignore
user.username = None  # type: ignore  # non-null field rejects None


# select()/alias()/noop() are generic over the model, so the concrete subclass
# flows through to iteration and get() instead of decaying to base Model.
assert_type(User.select(), ModelSelect[User])
assert_type(User.alias(), ModelAlias[User])
assert_type(User.alias().select(), ModelSelect[User])
assert_type(User.noop(), NoopModelSelect[User])

for u in User.select():
    assert_type(u, User)
for u in User.alias().select():
    assert_type(u, User)

assert_type(User.select().get(), User)
assert_type(User.select().get_or_none(), User | None)


# A `database=` argument accepts a real Database or a DatabaseProxy stand-in.
proxy = DatabaseProxy()
real_db = SqliteDatabase(':memory:')
SqliteDatabase(None)  # deferred init accepts None
real_db.init(None)  # ...as does init()

User.bind(proxy)
User.bind(real_db)
User.select().execute(proxy)
User.select().execute(real_db)
User.select().get(proxy)

User.select().execute('not a database')  # type: ignore


# chunked() preserves the element type of the source iterable.
assert_type(chunked([1, 2, 3], 2), Generator[list[int], None, None])

# Check() returns an SQL node, or a NodeList when a constraint name is given.
assert_type(Check('age > 0'), SQL | NodeList)
