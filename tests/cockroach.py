import datetime

from peewee import *
from playhouse.cockroach import *

from .base import IS_CRDB
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import requires_models
from .base import skip_unless
from .postgres_helpers import BaseBinaryJsonFieldTestCase


class KV(TestModel):
    k = TextField(unique=True)
    v = IntegerField()


class Arr(TestModel):
    title = TextField()
    tags = ArrayField(TextField, index=False)


class JsonModel(TestModel):
    data = JSONField()

class Normal(TestModel):
    data = TextField()


@skip_unless(IS_CRDB)
class TestCockroachDatabase(ModelTestCase):
    requires = [KV]

    def test_retry_transaction_ok(self):
        @self.database.retry_transaction()
        def succeeds(db):
            k1 = KV.create(k='k1', v=1)
            k2 = KV.create(k='k2', v=2)
            return [k1.id, k2.id]

        id_list = succeeds()
        self.assertEqual(KV.select().count(), 2)

        kv_list = [kv.id for kv in KV.select().order_by(KV.k)]
        self.assertEqual(kv_list, id_list)

    def test_retry_transaction_integrityerror(self):
        KV.create(k='kx', v=0)

        @self.database.retry_transaction()
        def fails(db):
            KV.create(k='k1', v=1)
            KV.create(k='kx', v=1)

        with self.assertRaises(IntegrityError):
            fails()

        self.assertEqual(KV.select().count(), 1)
        kv = KV.get(KV.k == 'kx')
        self.assertEqual(kv.v, 0)

    def test_run_transaction_helper(self):
        def succeeds(db):
            KV.insert_many([('k%s' % i, i) for i in range(10)]).execute()
        run_transaction(self.database, succeeds)
        self.assertEqual([(kv.k, kv.v) for kv in KV.select().order_by(KV.k)],
                         [('k%s' % i, i) for i in range(10)])

    @requires_models(Arr)
    def test_array_field(self):
        a1 = Arr.create(title='a1', tags=['t1', 't2'])
        a2 = Arr.create(title='a2', tags=['t2', 't3'])

        # Ensure we can read an array back.
        a1_db = Arr.get(Arr.title == 'a1')
        self.assertEqual(a1_db.tags, ['t1', 't2'])

        # Ensure we can filter on arrays.
        a2_db = Arr.get(Arr.tags == ['t2', 't3'])
        self.assertEqual(a2_db.id, a2.id)

        # Item lookups.
        a1_db = Arr.get(Arr.tags[1] == 't2')
        self.assertEqual(a1_db.id, a1.id)
        self.assertRaises(Arr.DoesNotExist, Arr.get, Arr.tags[2] == 'x')

    @requires_models(Arr)
    def test_array_field_search(self):
        def assertAM(where, id_list):
            query = Arr.select().where(where).order_by(Arr.title)
            self.assertEqual([a.id for a in query], id_list)

        data = (
            ('a1', ['t1', 't2']),
            ('a2', ['t2', 't3']),
            ('a3', ['t3', 't4']))
        id_list = Arr.insert_many(data).execute()
        a1, a2, a3 = [pk for pk, in id_list]

        assertAM(Value('t2') == fn.ANY(Arr.tags), [a1, a2])
        assertAM(Value('t1') == fn.Any(Arr.tags), [a1])
        assertAM(Value('tx') == fn.Any(Arr.tags), [])

        # Use the contains operator explicitly.
        assertAM(SQL("tags::text[] @> ARRAY['t2']"), [a1, a2])

        # Use the porcelain.
        assertAM(Arr.tags.contains('t2'), [a1, a2])
        assertAM(Arr.tags.contains('t3'), [a2, a3])
        assertAM(Arr.tags.contains('t1', 't2'), [a1])
        assertAM(Arr.tags.contains('t3', 't4'), [a3])
        assertAM(Arr.tags.contains('t2', 't3', 't4'), [])

        assertAM(Arr.tags.contains_any('t2'), [a1, a2])
        assertAM(Arr.tags.contains_any('t3'), [a2, a3])
        assertAM(Arr.tags.contains_any('t1', 't2'), [a1, a2])
        assertAM(Arr.tags.contains_any('t3', 't4'), [a2, a3])
        assertAM(Arr.tags.contains_any('t2', 't3', 't4'), [a1, a2, a3])

    @requires_models(Arr)
    def test_array_field_index(self):
        a1 = Arr.create(title='a1', tags=['a1', 'a2'])
        a2 = Arr.create(title='a2', tags=['a2', 'a3', 'a4', 'a5'])

        # NOTE: CRDB does not support array slicing.
        query = (Arr
                 .select(Arr.tags[1].alias('st'))
                 .order_by(Arr.title))
        self.assertEqual([a.st for a in query], ['a2', 'a3'])


class TestCockroachDatabaseJsonField(BaseBinaryJsonFieldTestCase, ModelTestCase):
    database = db
    M = JsonModel
    N = Normal
    requires = [JsonModel, Normal]
