"""
Support for using a dedicated read-slave. The read database is specified as a
Model.Meta option, and will be used for SELECT statements:


master = PostgresqlDatabase('master')
read_slave = PostgresqlDatabase('read_slave')

class BaseModel(ReadSlaveModel):
    class Meta:
        database = master
        read_slave = read_slave  # This database will be used for SELECTs.


# Now define your models as you would normally.
class User(BaseModel):
    username = CharField()

# To force a SELECT on the master database, you can instantiate the SelectQuery
# by hand:
master_select = SelectQuery(User).where(...)
"""
from peewee import *


class ReadSlaveModel(Model):
    @classmethod
    def select(cls, *args, **kwargs):
        query = super(ReadSlaveModel, cls).select(*args, **kwargs)
        if getattr(cls._meta, 'read_slave', None):
            query.database = cls._meta.read_slave
        return query

    @classmethod
    def raw(cls, *args, **kwargs):
        query = super(ReadSlaveModel, cls).raw(*args, **kwargs)
        if (getattr(cls._meta, 'read_slave', None) and
                query._sql.lower().startswith('select')):
            query.database = cls._meta.read_slave
        return query
