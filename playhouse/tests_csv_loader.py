import csv
import unittest
from contextlib import contextmanager
from datetime import date
from StringIO import StringIO
from textwrap import dedent

from playhouse.csv_loader import *


class TestRowConverter(RowConverter):
    @contextmanager
    def get_reader(self, csv_data, **reader_kwargs):
        reader = csv.reader(StringIO(csv_data), **reader_kwargs)
        yield reader

class TestLoader(Loader):
    @contextmanager
    def get_reader(self, csv_data, **reader_kwargs):
        reader = csv.reader(StringIO(csv_data), **reader_kwargs)
        yield reader

    def get_converter(self):
        return self.converter or TestRowConverter(
            self.database,
            has_header=self.has_header,
            sample_size=self.sample_size)

db = SqliteDatabase(':memory:')

class TestCSVConversion(unittest.TestCase):
    header = 'id,name,dob,salary,is_admin'
    simple = '10,"F1 L1",1983-01-01,10000,t'
    float_sal = '20,"F2 L2",1983-01-02,20000.5,f'
    only_name = ',"F3 L3",,,'
    mismatch = 'foo,F4 L4,dob,sal,x'

    def build_csv(self, *lines):
        return '\r\n'.join(lines)

    def load(self, *lines, **loader_kwargs):
        csv = self.build_csv(*lines)
        loader_kwargs['filename'] = csv
        loader_kwargs.setdefault('db_table', 'csv_test')
        loader_kwargs.setdefault('db_or_model', db)
        return TestLoader(**loader_kwargs).load()

    def assertData(self, ModelClass, expected):
        query = ModelClass.select().order_by(ModelClass.name).tuples()
        self.assertEqual([row[1:] for row in query], expected)

    def test_defaults(self):
        ModelClass = self.load(
            self.header,
            self.simple,
            self.float_sal,
            self.only_name)
        self.assertData(ModelClass, [
            (10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f'),
            (0, 'F3 L3', None, 0., ''),
        ])
