import datetime

from peewee import *
from playhouse.cockroach import *

from .base import IS_CRDB
from .base import ModelTestCase
from .base import TestModel
from .base import requires_models
from .base import skip_unless


class KV(TestModel):
    k = TextField(unique=True)
    v = IntegerField()


class Arr(TestModel):
    title = TextField()
    tags = ArrayField(TextField, index=False)


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
