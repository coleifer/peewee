from peewee import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import db
from .base_models import Register


class TestTransaction(ModelTestCase):
    requires = [Register]

    def test_transactions(self):
        def assertRegister(vals):
            query = Register.select().order_by(Register.value)
            self.assertEqual([register.value for register in query], vals)

        def save(*vals):
            Register.insert([{Register.value: val} for val in vals]).execute()

        self.assertFalse(db.in_transaction())

        with db.atomic():
            self.assertTrue(db.in_transaction())
            save(1)

        assertRegister([1])

        with db.atomic() as txn:
            save(2)
            txn.rollback()
            save(3)
            with db.atomic() as sp1:
                save(4)
                with db.atomic() as sp2:
                    save(5)
                    sp2.rollback()
                with db.atomic() as sp3:
                    save(6)
                    with db.atomic() as sp4:
                        save(7)
                        with db.atomic() as sp5:
                            save(8)
                        assertRegister([1, 3, 4, 6, 7, 8])
                        sp4.rollback()

                    assertRegister([1, 3, 4, 6])

        assertRegister([1, 3, 4, 6])
        Register.delete().execute()
        assertRegister([])

        with db.transaction() as txn:
            save(1)
            with db.transaction() as txn2:
                save(2)
                txn2.rollback()  # Actually issues a rollback.
                assertRegister([])
            save(3)
        assertRegister([3])
