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
