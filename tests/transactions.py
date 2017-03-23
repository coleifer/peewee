from peewee import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import db
from .base_models import Register


class TestTransaction(ModelTestCase):
    requires = [Register]

    def assertRegister(self, vals):
        query = Register.select().order_by(Register.value)
        self.assertEqual([register.value for register in query], vals)

    def _save(self, *vals):
        Register.insert([{Register.value: val} for val in vals]).execute()

    def test_transactions(self):
        self.assertFalse(db.in_transaction())

        with db.atomic():
            self.assertTrue(db.in_transaction())
            self._save(1)

        self.assertRegister([1])

        with db.atomic() as txn:
            self._save(2)
            txn.rollback()
            self._save(3)
            with db.atomic() as sp1:
                self._save(4)
                with db.atomic() as sp2:
                    self._save(5)
                    sp2.rollback()
                with db.atomic() as sp3:
                    self._save(6)
                    with db.atomic() as sp4:
                        self._save(7)
                        with db.atomic() as sp5:
                            self._save(8)
                        self.assertRegister([1, 3, 4, 6, 7, 8])
                        sp4.rollback()

                    self.assertRegister([1, 3, 4, 6])

        self.assertRegister([1, 3, 4, 6])

    def test_nested_transaction_obj(self):
        self.assertRegister([])

        with db.transaction() as txn:
            self._save(1)
            with db.transaction() as txn2:
                self._save(2)
                txn2.rollback()  # Actually issues a rollback.
                self.assertRegister([])
            self._save(3)
        self.assertRegister([3])

    def test_savepoint_commit(self):
        with db.atomic() as txn:
            self._save(1)
            txn.rollback()

            self._save(2)
            txn.commit()

            with db.atomic() as sp:
                self._save(3)
                sp.rollback()

                self._save(4)
                sp.commit()

        self.assertRegister([2, 4])
