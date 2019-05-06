from peewee import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import db
from .base_models import Register


class BaseTransactionTestCase(ModelTestCase):
    requires = [Register]

    def assertRegister(self, vals):
        query = Register.select().order_by(Register.value)
        self.assertEqual([register.value for register in query], vals)

    def _save(self, *vals):
        Register.insert([{Register.value: val} for val in vals]).execute()


class TestTransaction(BaseTransactionTestCase):
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

    def test_commit_rollback(self):
        with db.atomic() as txn:
            self._save(1)
            txn.commit()
            self._save(2)
            txn.rollback()

        self.assertRegister([1])

        with db.atomic() as txn:
            self._save(3)
            txn.rollback()
            self._save(4)

        self.assertRegister([1, 4])

    def test_commit_rollback_nested(self):
        with db.atomic() as txn:
            self.test_commit_rollback()
            txn.rollback()
        self.assertRegister([])

        with db.atomic():
            self.test_commit_rollback()
        self.assertRegister([1, 4])

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

    def test_atomic_decorator(self):
        @db.atomic()
        def save(i):
            self._save(i)

        save(1)
        self.assertRegister([1])

    def text_atomic_exception(self):
        def will_fail(self):
            with db.atomic():
                self._save(1)
                self._save(None)

        self.assertRaises(IntegrityError, will_fail)
        self.assertRegister([])

        def user_error(self):
            with db.atomic():
                self._save(2)
                raise ValueError

        self.assertRaises(ValueError, user_error)
        self.assertRegister([])

    def test_manual_commit(self):
        with db.manual_commit():
            db.begin()
            self._save(1)
            db.rollback()

            db.begin()
            self._save(2)
            db.commit()

            with db.manual_commit():
                db.begin()
                self._save(3)
                db.rollback()

            db.begin()
            self._save(4)
            db.commit()

        self.assertRegister([2, 4])

    def test_mixing_manual_atomic(self):
        @db.manual_commit()
        def will_fail():
            pass

        @db.atomic()
        def also_fails():
            pass

        with db.atomic():
            self.assertRaises(ValueError, will_fail)

        with db.manual_commit():
            self.assertRaises(ValueError, also_fails)

        with db.manual_commit():
            with self.assertRaises(ValueError):
                with db.atomic(): pass
        with db.atomic():
            with self.assertRaises(ValueError):
                with db.manual_commit(): pass

    def test_closing_db_in_transaction(self):
        with db.atomic():
            self.assertRaises(OperationalError, db.close)

    def test_db_context_manager(self):
        db.close()
        self.assertTrue(db.is_closed())

        with db:
            self.assertFalse(db.is_closed())
            self._save(1)
            with db:
                self._save(2)
                try:
                    with db:
                        self._save(3)
                        raise ValueError('xxx')
                except ValueError:
                    pass
                self._save(4)

            try:
                with db:
                    self._save(5)
                    with db:
                        self._save(6)
                    raise ValueError('yyy')
            except ValueError:
                pass

            self.assertFalse(db.is_closed())

        self.assertTrue(db.is_closed())
        self.assertRegister([1, 2, 4])


class TestSession(BaseTransactionTestCase):
    def test_session(self):
        self.assertTrue(db.session_start())
        self.assertTrue(db.session_start())
        self.assertEqual(db.transaction_depth(), 2)

        self._save(1)
        self.assertTrue(db.session_commit())
        self.assertEqual(db.transaction_depth(), 1)

        self._save(2)  # Now we're in autocommit mode.
        self.assertTrue(db.session_rollback())
        self.assertEqual(db.transaction_depth(), 0)

        self.assertTrue(db.session_start())
        self._save(3)
        self.assertTrue(db.session_rollback())
        self.assertRegister([1])

    def test_session_inside_context_manager(self):
        with db.atomic():
            self.assertTrue(db.session_start())
            self._save(1)
            self.assertTrue(db.session_commit())
            self._save(2)
            self.assertTrue(db.session_rollback())
            db.session_start()
            self._save(3)

        self.assertRegister([1, 3])

    def test_commit_rollback_mix(self):
        db.session_start()

        with db.atomic() as txn:  # Will be a savepoint.
            self._save(1)
            with db.atomic() as t2:
                self._save(2)
                with db.atomic() as t3:
                    self._save(3)
                t2.rollback()

            txn.commit()
            self._save(4)
            txn.rollback()

        self.assertTrue(db.session_commit())
        self.assertRegister([1])

    def test_session_rollback(self):
        db.session_start()

        self._save(1)
        with db.atomic() as txn:
            self._save(2)
            with db.atomic() as t2:
                self._save(3)

        self.assertRegister([1, 2, 3])
        self.assertTrue(db.session_rollback())
        self.assertRegister([])

        db.session_start()
        self._save(1)

        with db.transaction() as txn:
            self._save(2)
            with db.transaction() as t2:
                self._save(3)
                t2.rollback()  # Rolls back everything, starts new txn.

        db.session_commit()
        self.assertRegister([])

    def test_session_commit(self):
        db.session_start()

        self._save(1)
        with db.transaction() as txn:
            self._save(2)
            with db.transaction() as t2:
                self._save(3)
                t2.commit()  # Saves everything, starts new txn.
            txn.rollback()

        self.assertTrue(db.session_rollback())
        self.assertRegister([1, 2, 3])
