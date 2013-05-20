import itertools
import operator
import pickle
from peewee import *
from peewee import Leaf

try:
    from playhouse.apsw_ext import APSWDatabase
    def KeyValueDatabase(db_name):
        return APSWDatabase(db_name)
except ImportError:
    def KeyValueDatabase(db_name):
        return SqliteDatabase(db_name, check_same_thread=False)

Sentinel = type('Sentinel', (object,), {})

key_value_db = KeyValueDatabase(':memory:')

class PickleField(BlobField):
    def db_value(self, value):
        return pickle.dumps(value)

    def python_value(self, value):
        return pickle.loads(value)

class KeyStore(object):
    """
    Rich dictionary with support for storing a wide variety of data types.

    :param peewee.Field value_type: Field type to use for values.
    :param boolean ordered: Whether keys should be returned in sorted order.
    :param peewee.Model model: Model class to use for Keys/Values.
    """
    def __init__(self, value_field, ordered=False, database=None):
        self._value_field = value_field
        self._ordered = ordered

        self._database = database or key_value_db
        self._compiler = self._database.compiler()

        self.model = self.create_model()
        self.key = self.model.key
        self.value = self.model.value

        self._database.create_table(self.model, True)
        self._native_upsert = isinstance(self._database, SqliteDatabase)

    def create_model(self):
        class KVModel(Model):
            key = CharField(max_length=255, primary_key=True)
            value = self._value_field

            class Meta:
                database = self._database

        return KVModel

    def query(self, *select):
        query = self.model.select(*select).tuples()
        if self._ordered:
            query = query.order_by(self.key)
        return query

    def convert_expr(self, expr):
        if not isinstance(expr, Leaf):
            return (self.key == expr), True
        return expr, False

    def __contains__(self, key):
        expr, _ = self.convert_expr(key)
        return self.model.select().where(expr).exists()

    def __len__(self):
        return self.model.select().count()

    def __getitem__(self, expr):
        converted, is_single = self.convert_expr(expr)
        result = self.query(self.value).where(converted)
        item_getter = operator.itemgetter(0)
        result = [item_getter(val) for val in result]
        if len(result) == 0 and is_single:
            raise KeyError(expr)
        elif is_single:
            return result[0]
        return result

    def _upsert(self, key, value):
        sets, params = self._compiler.parse_field_dict({
            self.key: key,
            self.value: value})
        fields, interp = zip(*sets)
        sql = 'INSERT OR REPLACE INTO %s (%s) VALUES (%s)' % (
            self._compiler.quote(self.model._meta.db_table),
            ', '.join(fields),
            ', '.join(interp))
        self._database.execute_sql(sql, params, True)

    def __setitem__(self, expr, value):
        if isinstance(expr, Leaf):
            update = {self.value.name: value}
            self.model.update(**update).where(expr).execute()
        elif self._native_upsert:
            self._upsert(expr, value)
        else:
            try:
                self.model.create(key=expr, value=value)
            except:
                self._database.rollback()
                (self.model
                 .update(**{self.value.name: value})
                 .where(self.key == expr)
                 .execute())

    def __delitem__(self, expr):
        converted, _ = self.convert_expr(expr)
        self.model.delete().where(converted).execute()

    def __iter__(self):
        return self.query().execute()

    def keys(self):
        return map(operator.itemgetter(0), self.query(self.key))

    def values(self):
        return map(operator.itemgetter(0), self.query(self.value))

    def items(self):
        return iter(self)

    def get(self, k, default=None):
        try:
            return self[k]
        except KeyError:
            return default

    def pop(self, k, default=Sentinel):
        with self._database.transaction():
            expr, is_single = self.convert_expr(k)
            try:
                res = self[k]
            except KeyError:
                if default is Sentinel:
                    raise
                return default
            del(self[expr])
        return res

    def clear(self):
        self.model.delete().execute()


class PickledKeyStore(KeyStore):
    def __init__(self, ordered=False, database=None):
        super(PickledKeyStore, self).__init__(PickleField(), ordered, database)
