from peewee import *

from .base import ModelTestCase
from .base import TestModel
from .base import requires_postgresql


class T1(TestModel):
    pk = AutoField()
    value = IntegerField()

class T2(TestModel):
    pk = IntegerField(constraints=[SQL('DEFAULT 3')], primary_key=True)
    value = IntegerField()

class T3(TestModel):
    pk = IntegerField(primary_key=True)
    value = IntegerField()

class T4(TestModel):
    pk1 = IntegerField()
    pk2 = IntegerField()
    value = IntegerField()
    class Meta:
        primary_key = CompositeKey('pk1', 'pk2')

class T5(TestModel):
    val = IntegerField(null=True)


class TestPrimaryKeySaveHandling(ModelTestCase):
    requires = [T1, T2, T3, T4]

    def test_auto_field(self):
        # AutoField will be inserted if the PK is not set, after which the new
        # ID will be populated.
        t11 = T1(value=1)
        self.assertEqual(t11.save(), 1)
        self.assertTrue(t11.pk is not None)

        # Calling save() a second time will issue an update.
        t11.value = 100
        self.assertEqual(t11.save(), 1)

        # Verify the record was updated.
        t11_db = T1[t11.pk]
        self.assertEqual(t11_db.value, 100)

        # We can explicitly specify the value of an auto-incrementing
        # primary-key, but we must be sure to call save(force_insert=True),
        # otherwise peewee will attempt to do an update.
        t12 = T1(pk=1337, value=2)
        self.assertEqual(t12.save(), 0)
        self.assertEqual(T1.select().count(), 1)
        self.assertEqual(t12.save(force_insert=True), 1)

        # Attempting to force-insert an already-existing PK will fail with an
        # integrity error.
        with self.database.atomic():
            with self.assertRaises(IntegrityError):
                t12.value = 3
                t12.save(force_insert=True)

        query = T1.select().order_by(T1.value).tuples()
        self.assertEqual(list(query), [(1337, 2), (t11.pk, 100)])

    @requires_postgresql
    def test_server_default_pk(self):
        # The new value of the primary-key will be returned to us, since
        # postgres supports RETURNING.
        t2 = T2(value=1)
        self.assertEqual(t2.save(), 1)
        self.assertEqual(t2.pk, 3)

        # Saving after the PK is set will issue an update.
        t2.value = 100
        self.assertEqual(t2.save(), 1)

        t2_db = T2[3]
        self.assertEqual(t2_db.value, 100)

        # If we just set the pk and try to save, peewee issues an update which
        # doesn't have any effect.
        t22 = T2(pk=2, value=20)
        self.assertEqual(t22.save(), 0)
        self.assertEqual(T2.select().count(), 1)

        # We can force-insert the value we specify explicitly.
        self.assertEqual(t22.save(force_insert=True), 1)
        self.assertEqual(T2[2].value, 20)

    def test_integer_field_pk(self):
        # For a non-auto-incrementing primary key, we have to use force_insert.
        t3 = T3(pk=2, value=1)
        self.assertEqual(t3.save(), 0)  # Oops, attempts to do an update.
        self.assertEqual(T3.select().count(), 0)

        # Force to be an insert.
        self.assertEqual(t3.save(force_insert=True), 1)

        # Now we can update the value and call save() to issue an update.
        t3.value = 100
        self.assertEqual(t3.save(), 1)

        # Verify data is correct.
        t3_db = T3[2]
        self.assertEqual(t3_db.value, 100)

    def test_composite_pk(self):
        t4 = T4(pk1=1, pk2=2, value=10)

        # Will attempt to do an update on non-existant rows.
        self.assertEqual(t4.save(), 0)
        self.assertEqual(t4.save(force_insert=True), 1)

        # Modifying part of the composite PK and attempt an update will fail.
        t4.pk2 = 3
        t4.value = 30
        self.assertEqual(t4.save(), 0)

        t4.pk2 = 2
        self.assertEqual(t4.save(), 1)

        t4_db = T4[1, 2]
        self.assertEqual(t4_db.value, 30)

    @requires_postgresql
    def test_returning_object(self):
        query = T2.insert(value=10).returning(T2).objects()
        t2_db, = list(query)
        self.assertEqual(t2_db.pk, 3)
        self.assertEqual(t2_db.value, 10)


class TestSaveNoData(ModelTestCase):
    requires = [T5]

    def test_save_no_data(self):
        t5 = T5.create()
        self.assertTrue(t5.id >= 1)

        t5.val = 3
        t5.save()

        t5_db = T5.get(T5.id == t5.id)
        self.assertEqual(t5_db.val, 3)

        t5.val = None
        t5.save()

        t5_db = T5.get(T5.id == t5.id)
        self.assertTrue(t5_db.val is None)

    def test_save_no_data2(self):
        t5 = T5.create()

        t5_db = T5.get(T5.id == t5.id)
        t5_db.save()

        t5_db = T5.get(T5.id == t5.id)
        self.assertTrue(t5_db.val is None)

    def test_save_no_data3(self):
        t5 = T5.create()
        self.assertRaises(ValueError, t5.save)
