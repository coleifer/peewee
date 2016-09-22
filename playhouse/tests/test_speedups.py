import datetime
import unittest

from peewee import *
from playhouse import _speedups as speedups
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_in_memory_database(use_speedups=True)

class BaseModel(Model):
    class Meta:
        database = db

class Note(BaseModel):
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)


class TestResultWrappers(ModelTestCase):
    requires = [Note]

    def setUp(self):
        super(TestResultWrappers, self).setUp()
        for i in range(10):
            Note.create(content='note-%s' % i)

    def test_dirty_fields(self):
        note = Note.create(content='huey')
        self.assertFalse(note.is_dirty())
        self.assertEqual(note.dirty_fields, [])

        ndb = Note.get(Note.content == 'huey')
        self.assertFalse(ndb.is_dirty())
        self.assertEqual(ndb.dirty_fields, [])

        ndb.content = 'x'
        self.assertTrue(ndb.is_dirty())
        self.assertEqual(ndb.dirty_fields, ['content'])

    def test_gh_regression_1073_func_coerce(self):
        func = fn.GROUP_CONCAT(Note.id).alias('note_ids')
        query = Note.select(func)
        self.assertRaises(ValueError, query.get)

        query = Note.select(func.coerce(False))
        result = query.get().note_ids
        self.assertEqual(result, ','.join(str(i) for i in range(1, 11)))

    def test_tuple_results(self):
        query = Note.select().order_by(Note.id).tuples()
        qr = query.execute()
        self.assertTrue(isinstance(qr, speedups._TuplesQueryResultWrapper))

        results = list(qr)
        self.assertEqual(len(results), 10)
        first, last = results[0], results[-1]
        self.assertEqual(first[:2], (1, 'note-0'))
        self.assertEqual(last[:2], (10, 'note-9'))
        self.assertTrue(isinstance(first[2], datetime.datetime))

    def test_dict_results(self):
        query = Note.select().order_by(Note.id).dicts()
        qr = query.execute()
        self.assertTrue(isinstance(qr, speedups._DictQueryResultWrapper))

        results = list(qr)
        self.assertEqual(len(results), 10)
        first, last = results[0], results[-1]
        self.assertEqual(sorted(first.keys()), ['content', 'id', 'timestamp'])
        self.assertEqual(first['id'], 1)
        self.assertEqual(first['content'], 'note-0')
        self.assertTrue(isinstance(first['timestamp'], datetime.datetime))

        self.assertEqual(last['id'], 10)
        self.assertEqual(last['content'], 'note-9')

    def test_model_results(self):
        query = Note.select().order_by(Note.id)
        qr = query.execute()
        self.assertTrue(isinstance(qr, speedups._ModelQueryResultWrapper))

        results = list(qr)
        self.assertEqual(len(results), 10)
        first, last = results[0], results[-1]

        self.assertTrue(isinstance(first, Note))
        self.assertEqual(first.id, 1)
        self.assertEqual(first.content, 'note-0')
        self.assertTrue(isinstance(first.timestamp, datetime.datetime))

        self.assertEqual(last.id, 10)
        self.assertEqual(last.content, 'note-9')

    def test_aliases(self):
        query = (Note
                 .select(
                     Note.id,
                     Note.content.alias('ct'),
                     Note.timestamp.alias('ts'))
                 .order_by(Note.id))

        rows = list(query.tuples())
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0][:2], (1, 'note-0'))
        self.assertTrue(isinstance(rows[0][2], datetime.datetime))

        rows = list(query.dicts())
        first = rows[0]
        self.assertEqual(sorted(first.keys()), ['ct', 'id', 'ts'])
        self.assertEqual(first['id'], 1)
        self.assertEqual(first['ct'], 'note-0')
        self.assertTrue(isinstance(first['ts'], datetime.datetime))

        rows = list(query)
        first = rows[0]
        self.assertTrue(isinstance(first, Note))
        self.assertEqual(first.id, 1)
        self.assertEqual(first.ct, 'note-0')
        self.assertIsNone(first.content)
        self.assertTrue(isinstance(first.ts, datetime.datetime))

    def test_fill_cache(self):
        with self.assertQueryCount(1):
            query = Note.select().order_by(Note.id)
            qr = query.execute()
            qr.fill_cache(3)

            self.assertEqual(qr._ct, 3)
            self.assertEqual(len(qr._result_cache), 3)

            # No changes to result wrapper.
            notes = query[:3]
            self.assertEqual([n.id for n in notes], [1, 2, 3])
            self.assertEqual(qr._ct, 4)
            self.assertEqual(len(qr._result_cache), 4)
            self.assertFalse(qr._populated)

            qr.fill_cache(5)
            notes = query[:5]
            self.assertEqual([n.id for n in notes], [1, 2, 3, 4, 5])
            self.assertEqual(qr._ct, 6)
            self.assertEqual(len(qr._result_cache), 6)

            notes = query[:7]
            self.assertEqual([n.id for n in notes], [1, 2, 3, 4, 5, 6, 7])
            self.assertEqual(qr._ct, 8)
            self.assertFalse(qr._populated)

            qr.fill_cache()
            self.assertEqual(
                [n.id for n in query],
                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
            self.assertEqual(qr._ct, 10)
            self.assertTrue(qr._populated)
