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

    def setUp(self):
        db.execute_sql('drop table if exists csv_test;')

    def build_csv(self, *lines):
        return '\r\n'.join(lines)

    def load(self, *lines, **loader_kwargs):
        csv = self.build_csv(*lines)
        loader_kwargs['filename'] = csv
        loader_kwargs.setdefault('db_table', 'csv_test')
        loader_kwargs.setdefault('db_or_model', db)
        return TestLoader(**loader_kwargs).load()

    def assertData(self, ModelClass, expected):
        name_field = ModelClass._meta.get_fields()[2]
        query = ModelClass.select().order_by(name_field).tuples()
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

    def test_no_header(self):
        ModelClass = self.load(
            self.simple,
            self.float_sal,
            field_names=['f1', 'f2', 'f3', 'f4', 'f5'],
            has_header=False)
        self.assertEqual(ModelClass._meta.get_field_names(), [
            '_auto_pk', 'f1', 'f2', 'f3', 'f4', 'f5'])
        self.assertData(ModelClass, [
            (10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f')])

    def test_no_header_no_fieldnames(self):
        ModelClass = self.load(
            self.simple,
            self.float_sal,
            has_header=False)
        self.assertEqual(ModelClass._meta.get_field_names(), [
            '_auto_pk', 'field_0', 'field_1', 'field_2', 'field_3', 'field_4'])

    def test_mismatch_types(self):
        ModelClass = self.load(
            self.header,
            self.simple,
            self.mismatch)
        self.assertData(ModelClass, [
            ('10', 'F1 L1', '1983-01-01', '10000', 't'),
            ('foo', 'F4 L4', 'dob', 'sal', 'x')])

    def test_fields(self):
        fields = [
            IntegerField(),
            CharField(),
            DateField(),
            FloatField(),
            CharField()]
        ModelClass = self.load(
            self.header,
            self.simple,
            self.float_sal,
            fields=fields)
        self.assertEqual(
            map(type, fields),
            map(type, ModelClass._meta.get_fields()[1:]))
        self.assertData(ModelClass, [
            (10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f')])
