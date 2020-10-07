import datetime

from peewee import *
from playhouse.sqlite_changelog import ChangeLog
from playhouse.sqlite_ext import JSONField
from playhouse.sqlite_ext import SqliteExtDatabase

from .base import ModelTestCase
from .base import TestModel
from .base import requires_models
from .base import skip_unless
from .sqlite_helpers import json_installed


database = SqliteExtDatabase(':memory:', pragmas={'foreign_keys': 1})


class Person(TestModel):
    name = TextField()
    dob = DateField()


class Note(TestModel):
    person = ForeignKeyField(Person, on_delete='CASCADE')
    content = TextField()
    timestamp = TimestampField()
    status = IntegerField(default=0)


class CT1(TestModel):
    f1 = TextField()
    f2 = IntegerField(null=True)
    f3 = FloatField()
    fi = IntegerField()


class CT2(TestModel):
    data = JSONField()  # Diff of json?


changelog = ChangeLog(database)
CL = changelog.model


@skip_unless(json_installed(), 'requires sqlite json1')
class TestChangeLog(ModelTestCase):
    database = database
    requires = [Person, Note]

    def setUp(self):
        super(TestChangeLog, self).setUp()
        changelog.install(Person)
        changelog.install(Note, skip_fields=['timestamp'])
        self.last_index = 0

    def assertChanges(self, changes, last_index=None):
        last_index = last_index or self.last_index
        query = (CL
                 .select(CL.action, CL.table, CL.changes)
                 .order_by(CL.id)
                 .offset(last_index))
        accum = list(query.tuples())
        self.last_index += len(accum)
        self.assertEqual(accum, changes)

    def test_changelog(self):
        huey = Person.create(name='huey', dob=datetime.date(2010, 5, 1))
        zaizee = Person.create(name='zaizee', dob=datetime.date(2013, 1, 1))
        self.assertChanges([
            ('INSERT', 'person', {'name': [None, 'huey'],
                                  'dob': [None, '2010-05-01']}),
            ('INSERT', 'person', {'name': [None, 'zaizee'],
                                  'dob': [None, '2013-01-01']})])

        zaizee.dob = datetime.date(2013, 2, 2)
        zaizee.save()
        self.assertChanges([
            ('UPDATE', 'person', {'dob': ['2013-01-01', '2013-02-02']})])

        zaizee.name = 'zaizee-x'
        zaizee.dob = datetime.date(2013, 3, 3)
        zaizee.save()

        huey.save()  # No changes.

        self.assertChanges([
            ('UPDATE', 'person', {'name': ['zaizee', 'zaizee-x'],
                                  'dob': ['2013-02-02', '2013-03-03']}),
            ('UPDATE', 'person', {})])

        zaizee.delete_instance()
        self.assertChanges([
            ('DELETE', 'person', {'name': ['zaizee-x', None],
                                  'dob': ['2013-03-03', None]})])

        nh1 = Note.create(person=huey, content='huey1', status=1)
        nh2 = Note.create(person=huey, content='huey2', status=2)
        self.assertChanges([
            ('INSERT', 'note', {'person_id': [None, huey.id],
                                'content': [None, 'huey1'],
                                'status': [None, 1]}),
            ('INSERT', 'note', {'person_id': [None, huey.id],
                                'content': [None, 'huey2'],
                                'status': [None, 2]})])

        nh1.content = 'huey1-x'
        nh1.status = 0
        nh1.save()

        mickey = Person.create(name='mickey', dob=datetime.date(2009, 8, 1))
        nh2.person = mickey
        nh2.save()

        self.assertChanges([
            ('UPDATE', 'note', {'content': ['huey1', 'huey1-x'],
                                'status': [1, 0]}),
            ('INSERT', 'person', {'name': [None, 'mickey'],
                                  'dob': [None, '2009-08-01']}),
            ('UPDATE', 'note', {'person_id': [huey.id, mickey.id]})])

        mickey.delete_instance()
        self.assertChanges([
            ('DELETE', 'note', {'person_id': [mickey.id, None],
                                'content': ['huey2', None],
                                'status': [2, None]}),
            ('DELETE', 'person', {'name': ['mickey', None],
                                  'dob': ['2009-08-01', None]})])

    @requires_models(CT1)
    def test_changelog_details(self):
        changelog.install(CT1, skip_fields=['fi'], insert=False, delete=False)

        c1 = CT1.create(f1='v1', f2=1, f3=1.5, fi=0)
        self.assertChanges([])

        CT1.update(f1='v1-x', f2=2, f3=2.5, fi=1).execute()
        self.assertChanges([
            ('UPDATE', 'ct1', {
                'f1': ['v1', 'v1-x'],
                'f2': [1, 2],
                'f3': [1.5, 2.5]})])

        c1.f2 = None
        c1.save()  # Overwrites previously-changed fields.
        self.assertChanges([('UPDATE', 'ct1', {
            'f1': ['v1-x', 'v1'],
            'f2': [2, None],
            'f3': [2.5, 1.5]})])

        c1.delete_instance()
        self.assertChanges([])

    @requires_models(CT2)
    def test_changelog_jsonfield(self):
        changelog.install(CT2)

        ca = CT2.create(data={'k1': 'v1'})
        cb = CT2.create(data=['i0', 'i1', 'i2'])
        cc = CT2.create(data='hello')

        self.assertChanges([
            ('INSERT', 'ct2', {'data': [None, {'k1': 'v1'}]}),
            ('INSERT', 'ct2', {'data': [None, ['i0', 'i1', 'i2']]}),
            ('INSERT', 'ct2', {'data': [None, 'hello']})])

        ca.data['k1'] = 'v1-x'
        cb.data.append('i3')
        cc.data = 'world'

        ca.save()
        cb.save()
        cc.save()

        self.assertChanges([
            ('UPDATE', 'ct2', {'data': [{'k1': 'v1'}, {'k1': 'v1-x'}]}),
            ('UPDATE', 'ct2', {'data': [['i0', 'i1', 'i2'],
                                        ['i0', 'i1', 'i2', 'i3']]}),
            ('UPDATE', 'ct2', {'data': ['hello', 'world']})])

        cc.data = 13.37
        cc.save()
        self.assertChanges([('UPDATE', 'ct2', {'data': ['world', 13.37]})])

        ca.delete_instance()
        self.assertChanges([
            ('DELETE', 'ct2', {'data': [{'k1': 'v1-x'}, None]})])
