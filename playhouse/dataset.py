import datetime
from decimal import Decimal
import operator
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
import sys

from peewee import *
from playhouse.db_url import connect
from playhouse.migrate import migrate
from playhouse.migrate import SchemaMigrator
from playhouse.reflection import Introspector

if sys.version_info[0] == 3:
    basestring = str
    from functools import reduce


class DataSet(object):
    def __init__(self, url):
        self._url = url
        parse_result = urlparse(url)
        self._database_path = parse_result.path[1:]

        # Connect to the database.
        self._database = connect(url)
        self._database.connect()

        # Introspect the database and generate models.
        self._introspector = Introspector.from_database(self._database)
        self._models = self._introspector.generate_models()
        self._migrator = SchemaMigrator.from_database(self._database)

        class BaseModel(Model):
            class Meta:
                database = self._database
        self._base_model = BaseModel

    def __repr__(self):
        return '<DataSet: %s>' % self._database_path

    def __getitem__(self, table):
        return Table(self, table, self._models.get(table))

    @property
    def tables(self):
        return self._database.get_tables()

    def __contains__(self, table):
        return table in self.tables

    def connect(self):
        self._database.connect()

    def close(self):
        self._database.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._database.is_closed():
            self.close()

    def transaction(self):
        if self._database.transaction_depth() == 0:
            return self._database.transaction()
        else:
            return self._database.savepoint()


class Table(object):
    def __init__(self, dataset, name, model_class):
        self.dataset = dataset
        self.name = name
        if model_class is None:
            model_class = self._create_model()

        self.model_class = model_class

    def __repr__(self):
        return '<Table: %s>' % self.name

    def __len__(self):
        return self.find().count()

    def __iter__(self):
        return iter(self.find().iterator())

    def _create_model(self):
        return type(self.name.encode('utf-8'), (self.dataset._base_model,), {})

    def _guess_field_type(self, value):
        if isinstance(value, basestring):
            return TextField
        if isinstance(value, (datetime.date, datetime.datetime)):
            return DateTimeField
        elif value is True or value is False:
            return BooleanField
        elif isinstance(value, int):
            return IntegerField
        elif isinstance(value, float):
            return FloatField
        elif isinstance(value, Decimal):
            return DecimalField
        return TextField

    @property
    def columns(self):
        return self.model_class._meta.get_field_names()

    def _migrate_new_columns(self, data):
        new_keys = set(data) - set(self.model_class._meta.fields)
        if new_keys:
            operations = []
            for key in new_keys:
                field_class = self._guess_field_type(data[key])
                field = field_class(null=True)
                operations.append(
                    self.dataset._migrator.add_column(self.name, key, field))
                field.add_to_class(self.model_class, key)

            migrate(*operations)

    def insert(self, **data):
        self._migrate_new_columns(data)
        return self.model_class.insert(**data).execute()

    def _apply_where(self, query, filters, conjunction=None):
        conjunction = conjunction or operator.and_
        if filters:
            expressions = [
                (self.model_class._meta.fields[column] == value)
                for column, value in filters.items()]
            query = query.where(reduce(conjunction, expressions))
        return query

    def update(self, columns=None, conjunction=None, **data):
        self._migrate_new_columns(data)
        filters = {}
        if columns:
            for column in columns:
                filters[column] = data.pop(column)

        return self._apply_where(
            self.model_class.update(**data),
            filters,
            conjunction).execute()

    def _query(self, **query):
        return self._apply_where(self.model_class.select(), query)

    def find(self, **query):
        return self._query(**query).dicts()

    def find_one(self, **query):
        try:
            return self.find(**query).get()
        except self.model_class.DoesNotExist:
            return None

    def all(self):
        return self.find()

    def delete(self, **query):
        return self._apply_where(self.model_class.delete(), query).execute()
