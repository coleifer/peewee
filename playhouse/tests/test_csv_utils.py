import csv
import datetime
from contextlib import contextmanager
from datetime import date
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
from textwrap import dedent

from peewee import *
from playhouse.csv_utils import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase


class TestRowConverter(RowConverter):
    @contextmanager
    def get_reader(self, csv_data, **reader_kwargs):
        reader = csv.reader(StringIO(csv_data), **reader_kwargs)
        yield reader


class TestBooleanRowConverter(RowConverter):
    @convert_field(BooleanField, default=False)
    def is_boolean(self, value):
        return value in ('TRUE', 'FALSE')

    def get_checks(self):
        checks = super(TestBooleanRowConverter, self).get_checks()
        checks.insert(-1, self.is_boolean)
        return checks


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


db = database_initializer.get_in_memory_database()


class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField()

class Note(BaseModel):
    user = ForeignKeyField(User)
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)
    is_published = BooleanField(default=True)


class TestCustomConverter(PeeweeTestCase):
    def setUp(self):
        super(TestCustomConverter, self).setUp()
        self.db = database_initializer.get_in_memory_database()

    def tearDown(self):
        if not self.db.is_closed():
            self.db.close()
        super(TestCustomConverter, self).tearDown()

    def test_custom_converter(self):
        csv_data = StringIO('\r\n'.join((
            'username,enabled,last_login',
            'charlie,TRUE,2015-01-02 00:00:00',
            'huey,FALSE,2015-02-03 00:00:00',
            'zaizee,,2015-03-04 00:00:00',
        )))
        converter = TestBooleanRowConverter(self.db)
        ModelClass = load_csv(self.db, csv_data, converter=converter)
        self.assertEqual(sorted(ModelClass._meta.fields.keys()), [
            '_auto_pk',
            'enabled',
            'last_login',
            'username'])
        self.assertTrue(isinstance(ModelClass.enabled, BooleanField))
        self.assertTrue(isinstance(ModelClass.last_login, DateTimeField))
        self.assertTrue(isinstance(ModelClass.username, BareField))


class TestCSVConversion(PeeweeTestCase):
    header = 'id,name,dob,salary,is_admin'
    simple = '10,"F1 L1",1983-01-01,10000,t'
    float_sal = '20,"F2 L2",1983-01-02,20000.5,f'
    only_name = ',"F3 L3",,,'
    mismatch = 'foo,F4 L4,dob,sal,x'

    def setUp(self):
        super(TestCSVConversion, self).setUp()
        db.execute_sql('drop table if exists csv_test;')

    def build_csv(self, *lines):
        return '\r\n'.join(lines)

    def load(self, *lines, **loader_kwargs):
        csv = self.build_csv(*lines)
        loader_kwargs['file_or_name'] = csv
        loader_kwargs.setdefault('db_table', 'csv_test')
        loader_kwargs.setdefault('db_or_model', db)
        return TestLoader(**loader_kwargs).load()

    def assertData(self, ModelClass, expected):
        name_field = ModelClass._meta.sorted_fields[1]
        query = ModelClass.select().order_by(name_field).tuples()
        self.assertEqual([row for row in query], expected)

    def test_defaults(self):
        ModelClass = self.load(
            self.header,
            self.simple,
            self.float_sal,
            self.only_name)
        self.assertData(ModelClass, [
            (10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f'),
            (21, 'F3 L3', None, 0., ''),
        ])

    def test_no_header(self):
        ModelClass = self.load(
            self.simple,
            self.float_sal,
            field_names=['f1', 'f2', 'f3', 'f4', 'f5'],
            has_header=False)
        self.assertEqual(ModelClass._meta.sorted_field_names, [
            '_auto_pk', 'f1', 'f2', 'f3', 'f4', 'f5'])
        self.assertData(ModelClass, [
            (1, 10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (2, 20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f')])

    def test_no_header_no_fieldnames(self):
        ModelClass = self.load(
            self.simple,
            self.float_sal,
            has_header=False)
        self.assertEqual(ModelClass._meta.sorted_field_names, [
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
            PrimaryKeyField(),
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
            list(map(type, fields)),
            list(map(type, ModelClass._meta.sorted_fields)))
        self.assertData(ModelClass, [
            (10, 'F1 L1', date(1983, 1, 1), 10000., 't'),
            (20, 'F2 L2', date(1983, 1, 2), 20000.5, 'f')])


class TestCSVDump(ModelTestCase):
    requires = [Note, User]

    def setUp(self):
        super(TestCSVDump, self).setUp()

        self.users = []
        for i in range(3):
            user = User.create(username='user-%s' % i)
            for j in range(i * 3):
                Note.create(
                    user=user,
                    content='note-%s-%s' % (i, j),
                    timestamp=datetime.datetime(2014, 1 + i, 1 + j),
                    is_published=j % 2 == 0)
            self.users.append(user)

    def assertCSV(self, query, csv_lines, **kwargs):
        buf = StringIO()
        kwargs['close_file'] = False  # Do not close the StringIO object.
        final_buf = dump_csv(query, buf, **kwargs)
        self.assertEqual(final_buf.getvalue().splitlines(), csv_lines)

    def test_dump_simple(self):
        expected = [
            'id,username',
            '%s,user-0' % self.users[0].id,
            '%s,user-1' % self.users[1].id,
            '%s,user-2' % self.users[2].id]

        self.assertCSV(User.select().order_by(User.id), expected)
        self.assertCSV(
            User.select().order_by(User.id),
            expected[1:],
            include_header=False)

        user_0_id = self.users[0].id
        self.users[0].username = '"herps", derp'
        self.users[0].save()
        query = User.select().where(User.id == user_0_id)
        self.assertCSV(query, [
            'id,username',
            '%s,"""herps"", derp"' % user_0_id])

    def test_dump_functions(self):
        query = (User
                 .select(User.username, fn.COUNT(Note.id))
                 .join(Note, JOIN.LEFT_OUTER)
                 .group_by(User.username)
                 .order_by(User.id))
        expected = [
            'username,COUNT',
            'user-0,0',
            'user-1,3',
            'user-2,6']
        self.assertCSV(query, expected)

        query = query.select(
            User.username.alias('name'),
            fn.COUNT(Note.id).alias('num_notes'))
        expected[0] = 'name,num_notes'
        self.assertCSV(query, expected)

    def test_dump_field_types(self):
        query = (Note
                 .select(
                     User.username,
                     Note.content,
                     Note.timestamp,
                     Note.is_published)
                 .join(User)
                 .order_by(Note.id))
        expected = [
            'username,content,timestamp,is_published',
            'user-1,note-1-0,2014-02-01 00:00:00,True',
            'user-1,note-1-1,2014-02-02 00:00:00,False',
            'user-1,note-1-2,2014-02-03 00:00:00,True',
            'user-2,note-2-0,2014-03-01 00:00:00,True',
            'user-2,note-2-1,2014-03-02 00:00:00,False',
            'user-2,note-2-2,2014-03-03 00:00:00,True',
            'user-2,note-2-3,2014-03-04 00:00:00,False',
            'user-2,note-2-4,2014-03-05 00:00:00,True',
            'user-2,note-2-5,2014-03-06 00:00:00,False']
        self.assertCSV(query, expected)
