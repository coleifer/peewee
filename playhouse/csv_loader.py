"""
Peewee helper for loading CSV data into a database.

Load the users CSV file into the database and return a Model for accessing
the data:

    from playhouse.csv_loader import load_csv
    db = SqliteDatabase(':memory:')
    User = load_csv(db, 'users.csv')

Provide explicit field types and/or field names:

    fields = [IntegerField(), IntegerField(), DateTimeField(), DecimalField()]
    field_names = ['from_acct', 'to_acct', 'timestamp', 'amount']
    Payments = load_csv(db, 'payments.csv', fields, field_names)
"""
import csv
import datetime
import os
import re
from collections import OrderedDict
from contextlib import contextmanager

from peewee import *
from peewee import Database


class _CSVReader(object):
    @contextmanager
    def get_reader(self, filename, **reader_kwargs):
        fh = open(filename, 'r')
        reader = csv.reader(fh, **reader_kwargs)
        yield reader
        fh.close()

class RowConverter(_CSVReader):
    """
    Simple introspection utility to convert a CSV file into a list of headers
    and column types.

    :param database: a peewee Database object.
    :param bool has_header: whether the first row of CSV is a header row.
    :param int sample_size: number of rows to introspect
    """
    date_formats = [
        '%Y-%m-%d',
        '%m/%d/%Y']

    datetime_formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f']

    def __init__(self, database, has_header=True, sample_size=10):
        self.database = database
        self.has_header = has_header
        self.sample_size = sample_size

    def matches_date(self, value, formats):
        for fmt in formats:
            try:
                datetime.datetime.strptime(value, fmt)
            except ValueError:
                pass
            else:
                return True

    def field(field_class, **field_kwargs):
        def decorator(fn):
            fn.field = lambda: field_class(**field_kwargs)
            return fn
        return decorator

    @field(IntegerField, default=0)
    def is_integer(self, value):
        return value.isdigit()

    @field(FloatField, default=0)
    def is_float(self, value):
        try:
            float(value)
        except (ValueError, TypeError):
            pass
        else:
            return True

    @field(DateTimeField, null=True)
    def is_datetime(self, value):
        return self.matches_date(value, self.datetime_formats)

    @field(DateField, null=True)
    def is_date(self, value):
        return self.matches_date(value, self.date_formats)

    @field(BareField, default='')
    def default(self, value):
        return True

    def extract_rows(self, filename, **reader_kwargs):
        """
        Extract `self.sample_size` rows from the CSV file and analyze their
        data-types.

        :param str filename: A string filename.
        :param reader_kwargs: Arbitrary parameters to pass to the CSV reader.
        :returns: A 2-tuple containing a list of headers and list of rows
                  read from the CSV file.
        """
        rows = []
        rows_to_read = self.sample_size
        with self.get_reader(filename, **reader_kwargs) as reader:
            if self.has_header:
                rows_to_read += 1
            for i, row in enumerate(reader):
                rows.append(row)
                if i == self.sample_size:
                    break
        if self.has_header:
            header, rows = rows[0], rows[1:]
        else:
            header = ['field_%d' % i for i in range(len(rows[0]))]
        return header, rows

    def get_checks(self):
        """Return a list of functions to use when testing values."""
        return [
            self.is_date,
            self.is_datetime,
            self.is_integer,
            self.is_float,
            self.default]

    def analyze(self, rows):
        """
        Analyze the given rows and try to determine the type of value stored.

        :param list rows: A list-of-lists containing one or more rows from a
                          csv file.
        :returns: A list of peewee Field objects for each column in the CSV.
        """
        transposed = zip(*rows)
        checks = self.get_checks()
        column_types = []
        for i, column in enumerate(transposed):
            # Remove any empty values.
            col_vals = [val for val in column if val != '']
            for check in checks:
                results = set(check(val) for val in col_vals)
                if all(results):
                    column_types.append(check.field())
                    break

        return column_types


class Loader(_CSVReader):
    """
    Load the contents of a CSV file into a database and return a model class
    suitable for working with the CSV data.

    :param db_or_model: a peewee Database instance or a Model class.
    :param str filename: the filename of the CSV file.
    :param list fields: A list of peewee Field() instances appropriate to
        the values in the CSV file.
    :param list field_names: A list of names to use for the fields.
    :param bool has_header: Whether the first row of the CSV file is a header.
    :param int sample_size: Number of rows to introspect if fields are not
        defined.
    :param converter: A RowConverter instance to use.
    :param str db_table: Name of table to store data in (if not specified, the
        table name will be derived from the CSV filename).
    :param reader_kwargs: Arbitrary arguments to pass to the CSV reader.
    """
    def __init__(self, db_or_model, filename, fields=None, field_names=None,
                 has_header=True, sample_size=10, converter=None,
                 db_table=None, **reader_kwargs):
        self.filename = filename
        self.fields = fields
        self.field_names = field_names
        self.has_header = has_header
        self.sample_size = sample_size
        self.converter = converter
        self.reader_kwargs = reader_kwargs

        if isinstance(db_or_model, Database):
            self.database = db_or_model
            self.model = None
            self.db_table = (db_table or
                             os.path.splitext(os.path.basename(filename))[0])
        else:
            self.model = db_or_model
            self.database = self.model._meta.database
            self.db_table = self.model._meta.db_table
            self.fields = self.model._meta.get_fields()
            self.field_names = self.model._meta.get_field_names()
            # If using an auto-incrementing primary key, ignore it.
            if self.model._meta.auto_increment:
                self.fields = self.fields[1:]
                self.field_names = self.field_names[1:]

    def clean_field_name(self, s):
        return re.sub('[^a-z0-9]+', '_', s.lower())

    def get_converter(self):
        return self.converter or RowConverter(
            self.database,
            has_header=self.has_header,
            sample_size=self.sample_size)

    def analyze_csv(self):
        converter = self.get_converter()
        header, rows = converter.extract_rows(
            self.filename,
            **self.reader_kwargs)
        if rows:
            self.fields = converter.analyze(rows)
        else:
            self.fields = [converter.default.field() for _ in header]
        if not self.field_names:
            self.field_names = map(self.clean_field_name, header)

    def get_model_class(self, field_names, fields):
        if self.model:
            return self.model
        attrs = dict(zip(field_names, fields))
        attrs['_auto_pk'] = PrimaryKeyField()
        klass = type(self.db_table.title(), (Model,), attrs)
        klass._meta.database = self.database
        klass._meta.db_table = self.db_table
        return klass

    def load(self):
        if not self.fields:
            self.analyze_csv()
        if not self.field_names and not self.has_header:
            self.field_names = [
                'field_%d' % i for i in range(len(self.fields))]

        with self.get_reader(self.filename, **self.reader_kwargs) as reader:
            if not self.field_names:
                self.field_names = map(self.clean_field_name, reader.next())
            elif self.has_header:
                reader.next()

            ModelClass = self.get_model_class(self.field_names, self.fields)

            with self.database.transaction():
                ModelClass.create_table(True)
                for row in reader:
                    insert = {}
                    for field_name, value in zip(self.field_names, row):
                        if value:
                            insert[field_name] = value.decode('utf-8')
                    if insert:
                        ModelClass.insert(**insert).execute()

        return ModelClass

def load_csv(db_or_model, filename, fields=None, field_names=None,
             has_header=True, sample_size=10, converter=None,
             db_table=None, **reader_kwargs):
    loader = Loader(db_or_model, filename, fields, field_names, has_header,
                    sample_size, converter, db_table, **reader_kwargs)
    return loader.load()
load_csv.__doc__ = Loader.__doc__
