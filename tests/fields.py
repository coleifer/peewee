import datetime
import sqlite3
import uuid
from decimal import Decimal as D
from decimal import ROUND_UP

from peewee import bytes_type
from peewee import *

from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_sqlite
from .base import skip_if
from .base_models import Tweet
from .base_models import User


class IntModel(TestModel):
    value = IntegerField()
    value_null = IntegerField(null=True)


class TestCoerce(ModelTestCase):
    requires = [IntModel]

    def test_coerce(self):
        i = IntModel.create(value='1337', value_null=3.14159)
        i_db = IntModel.get(IntModel.id == i.id)
        self.assertEqual(i_db.value, 1337)
        self.assertEqual(i_db.value_null, 3)


class DefaultValues(TestModel):
    data = IntegerField(default=17)
    data_callable = IntegerField(default=lambda: 1337)


class TestTextField(TextField):
    def first_char(self):
        return fn.SUBSTR(self, 1, 1)


class PhoneBook(TestModel):
    name = TestTextField()


class Bits(TestModel):
    F_STICKY = 1
    F_FAVORITE = 2
    F_MINIMIZED = 4

    flags = BitField()
    is_sticky = flags.flag(F_STICKY)
    is_favorite = flags.flag(F_FAVORITE)
    is_minimized = flags.flag(F_MINIMIZED)

    data = BigBitField()


class TestDefaultValues(ModelTestCase):
    requires = [DefaultValues]

    def test_default_values(self):
        d = DefaultValues()
        self.assertEqual(d.data, 17)
        self.assertEqual(d.data_callable, 1337)
        d.save()

        d_db = DefaultValues.get(DefaultValues.id == d.id)
        self.assertEqual(d_db.data, 17)
        self.assertEqual(d_db.data_callable, 1337)

    def test_defaults_create(self):
        d = DefaultValues.create()
        self.assertEqual(d.data, 17)
        self.assertEqual(d.data_callable, 1337)

        d_db = DefaultValues.get(DefaultValues.id == d.id)
        self.assertEqual(d_db.data, 17)
        self.assertEqual(d_db.data_callable, 1337)


class TestNullConstraint(ModelTestCase):
    requires = [IntModel]

    def test_null(self):
        i = IntModel.create(value=1)
        i_db = IntModel.get(IntModel.value == 1)
        self.assertIsNone(i_db.value_null)

    def test_empty_value(self):
        with self.database.atomic():
            with self.assertRaisesCtx(IntegrityError):
                IntModel.create(value=None)


class TestIntegerField(ModelTestCase):
    requires = [IntModel]

    def test_integer_field(self):
        i1 = IntModel.create(value=1)
        i2 = IntModel.create(value=2, value_null=20)

        vals = [(i.value, i.value_null)
                for i in IntModel.select().order_by(IntModel.value)]
        self.assertEqual(vals, [
            (1, None),
            (2, 20)])


class FloatModel(TestModel):
    value = FloatField()
    value_null = FloatField(null=True)


class TestFloatField(ModelTestCase):
    requires = [FloatModel]

    def test_float_field(self):
        f1 = FloatModel.create(value=1.23)
        f2 = FloatModel.create(value=3.14, value_null=0.12)

        query = FloatModel.select().order_by(FloatModel.id)
        self.assertEqual([(f.value, f.value_null) for f in query],
                         [(1.23, None), (3.14, 0.12)])


class DecimalModel(TestModel):
    value = DecimalField(decimal_places=2, auto_round=True)
    value_up = DecimalField(decimal_places=2, auto_round=True,
                            rounding=ROUND_UP, null=True)


class TestDecimalField(ModelTestCase):
    requires = [DecimalModel]

    def test_decimal_field(self):
        d1 = DecimalModel.create(value=D('3'))
        d2 = DecimalModel.create(value=D('100.33'))

        self.assertEqual(sorted(d.value for d in DecimalModel.select()),
                         [D('3'), D('100.33')])

    def test_decimal_rounding(self):
        d = DecimalModel.create(value=D('1.2345'), value_up=D('1.2345'))
        d_db = DecimalModel.get(DecimalModel.id == d.id)
        self.assertEqual(d_db.value, D('1.23'))
        self.assertEqual(d_db.value_up, D('1.24'))


class BoolModel(TestModel):
    value = BooleanField(null=True)
    name = CharField()


class TestBooleanField(ModelTestCase):
    requires = [BoolModel]

    def test_boolean_field(self):
        BoolModel.create(value=True, name='t')
        BoolModel.create(value=False, name='f')
        BoolModel.create(value=None, name='n')

        vals = sorted((b.name, b.value) for b in BoolModel.select())
        self.assertEqual(vals, [
            ('f', False),
            ('n', None),
            ('t', True)])


class DateModel(TestModel):
    date = DateField(null=True)
    time = TimeField(null=True)
    date_time = DateTimeField(null=True)


class CustomDateTimeModel(TestModel):
    date_time = DateTimeField(formats=[
        '%m/%d/%Y %I:%M %p',
        '%Y-%m-%d %H:%M:%S'])


class TestDateFields(ModelTestCase):
    requires = [DateModel]

    @requires_models(CustomDateTimeModel)
    def test_date_time_custom_format(self):
        cdtm = CustomDateTimeModel.create(date_time='01/02/2003 01:37 PM')
        cdtm_db = CustomDateTimeModel[cdtm.id]
        self.assertEqual(cdtm_db.date_time,
                         datetime.datetime(2003, 1, 2, 13, 37, 0))

    def test_date_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)

        if isinstance(self.database, MySQLDatabase):
            dt1 = dt1.replace(microsecond=0)
            t1 = t1.replace(microsecond=0)

        dm1 = DateModel.create(date_time=dt1, date=d1, time=t1)
        dm2 = DateModel.create(date_time=dt2, time=t2)

        dm1_db = DateModel.get(DateModel.id == dm1.id)
        self.assertEqual(dm1_db.date, d1)
        self.assertEqual(dm1_db.date_time, dt1)
        self.assertEqual(dm1_db.time, t1)

        dm2_db = DateModel.get(DateModel.id == dm2.id)
        self.assertEqual(dm2_db.date, None)
        self.assertEqual(dm2_db.date_time, dt2)
        self.assertEqual(dm2_db.time, t2)

    def test_extract_parts(self):
        dm = DateModel.create(
            date_time=datetime.datetime(2011, 1, 2, 11, 12, 13, 54321),
            date=datetime.date(2012, 2, 3),
            time=datetime.time(3, 13, 37))
        query = (DateModel
                 .select(DateModel.date_time.year, DateModel.date_time.month,
                         DateModel.date_time.day, DateModel.date_time.hour,
                         DateModel.date_time.minute,
                         DateModel.date_time.second, DateModel.date.year,
                         DateModel.date.month, DateModel.date.day,
                         DateModel.time.hour, DateModel.time.minute,
                         DateModel.time.second)
                 .tuples())

        row, = query
        if IS_SQLITE or IS_MYSQL:
            self.assertEqual(row,
                             (2011, 1, 2, 11, 12, 13, 2012, 2, 3, 3, 13, 37))
        elif IS_POSTGRESQL:
            self.assertEqual(row, (
                2011., 1., 2., 11., 12., 13.054321, 2012., 2., 3., 3., 13.,
                37.))

    def test_distinct_date_part(self):
        years = (1980, 1990, 2000, 2010)
        for i, year in enumerate(years):
            for j in range(i + 1):
                DateModel.create(date=datetime.date(year, i + 1, 1))

        query = (DateModel
                 .select(DateModel.date.year.distinct())
                 .order_by(DateModel.date.year))
        self.assertEqual([year for year, in query.tuples()],
                         [1980, 1990, 2000, 2010])


class U2(TestModel):
    username = TextField()


class T2(TestModel):
    user = ForeignKeyField(U2, backref='tweets', on_delete='CASCADE')
    content = TextField()


class TestForeignKeyField(ModelTestCase):
    requires = [User, Tweet]

    def test_set_fk(self):
        huey = User.create(username='huey')
        zaizee = User.create(username='zaizee')

        # Test resolution of attributes after creation does not trigger SELECT.
        with self.assertQueryCount(1):
            tweet = Tweet.create(content='meow', user=huey)
            self.assertEqual(tweet.user.username, 'huey')

        # Test we can set to an integer, in which case a query will occur.
        with self.assertQueryCount(2):
            tweet = Tweet.create(content='purr', user=zaizee.id)
            self.assertEqual(tweet.user.username, 'zaizee')

        # Test we can set the ID accessor directly.
        with self.assertQueryCount(2):
            tweet = Tweet.create(content='hiss', user_id=huey.id)
            self.assertEqual(tweet.user.username, 'huey')

    def test_follow_attributes(self):
        huey = User.create(username='huey')
        Tweet.create(content='meow', user=huey)
        Tweet.create(content='hiss', user=huey)

        with self.assertQueryCount(1):
            query = (Tweet
                     .select(Tweet.content, Tweet.user.username)
                     .join(User)
                     .order_by(Tweet.content))
            self.assertEqual([(tweet.content, tweet.user.username)
                              for tweet in query],
                             [('hiss', 'huey'), ('meow', 'huey')])

        self.assertRaises(AttributeError, lambda: Tweet.user.foo)

    def test_disable_backref(self):
        class Person(TestModel):
            pass
        class Pet(TestModel):
            owner = ForeignKeyField(Person, backref='!')

        self.assertEqual(Pet.owner.backref, '!')

        # No attribute/accessor is added to the related model.
        self.assertRaises(AttributeError, lambda: Person.pet_set)

        # We still preserve the metadata about the relationship.
        self.assertTrue(Pet.owner in Person._meta.backrefs)

    @requires_models(U2, T2)
    def test_on_delete_behavior(self):
        if IS_SQLITE:
            self.database.foreign_keys = 1

        with self.database.atomic():
            for username in ('u1', 'u2', 'u3'):
                user = U2.create(username=username)
                for i in range(3):
                    T2.create(user=user, content='%s-%s' % (username, i))

        self.assertEqual(T2.select().count(), 9)
        U2.delete().where(U2.username == 'u2').execute()
        self.assertEqual(T2.select().count(), 6)

        query = (U2
                 .select(U2.username, fn.COUNT(T2.id).alias('ct'))
                 .join(T2, JOIN.LEFT_OUTER)
                 .group_by(U2.username)
                 .order_by(U2.username))
        self.assertEqual([(u.username, u.ct) for u in query], [
            ('u1', 3),
            ('u3', 3)])


class M1(TestModel):
    name = CharField(primary_key=True)
    m2 = DeferredForeignKey('M2', deferrable='INITIALLY DEFERRED',
                            on_delete='CASCADE')

class M2(TestModel):
    name = CharField(primary_key=True)
    m1 = ForeignKeyField(M1, deferrable='INITIALLY DEFERRED',
                         on_delete='CASCADE')


@skip_if(IS_MYSQL)
class TestDeferredForeignKey(ModelTestCase):
    requires = [M1, M2]

    def test_deferred_foreign_key(self):
        with self.database.atomic():
            m1 = M1.create(name='m1', m2='m2')
            m2 = M2.create(name='m2', m1='m1')

        m1_db = M1.get(M1.name == 'm1')
        self.assertEqual(m1_db.m2.name, 'm2')

        m2_db = M2.get(M2.name == 'm2')
        self.assertEqual(m2_db.m1.name, 'm1')


class Composite(TestModel):
    first = CharField()
    last = CharField()
    data = TextField()

    class Meta:
        primary_key = CompositeKey('first', 'last')


class TestCompositePrimaryKeyField(ModelTestCase):
    requires = [Composite]

    def test_composite_primary_key(self):
        pass


class TestFieldFunction(ModelTestCase):
    requires = [PhoneBook]

    def setUp(self):
        super(TestFieldFunction, self).setUp()
        names = ('huey', 'mickey', 'zaizee', 'beanie', 'scout', 'hallee')
        for name in names:
            PhoneBook.create(name=name)

    def _test_field_function(self, PB):
        query = (PB
                 .select()
                 .where(PB.name.first_char() == 'h')
                 .order_by(PB.name))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" '
            'FROM "phone_book" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?) '
            'ORDER BY "t1"."name"'), [1, 1, 'h'])

        self.assertEqual([pb.name for pb in query], ['hallee', 'huey'])

    def test_field_function(self):
        self._test_field_function(PhoneBook)

    def test_field_function_alias(self):
        self._test_field_function(PhoneBook.alias())


class IPModel(TestModel):
    ip = IPField()
    ip_null = IPField(null=True)


class TestIPField(ModelTestCase):
    requires = [IPModel]

    def test_ip_field(self):
        ips = ('0.0.0.0', '255.255.255.255', '192.168.1.1')
        for ip in ips:
            i = IPModel.create(ip=ip)
            i_db = IPModel.get(ip=ip)
            self.assertEqual(i_db.ip, ip)
            self.assertEqual(i_db.ip_null, None)


class TestBitFields(ModelTestCase):
    requires = [Bits]

    def test_bit_field_auto_flag(self):
        class Bits2(TestModel):
            flags = BitField()

            f1 = flags.flag()  # Automatically gets 1.
            f2 = flags.flag()  # 2
            f4 = flags.flag()  # 4
            f16 = flags.flag(16)
            f32 = flags.flag()  # 32

        b = Bits2()
        self.assertEqual(b.flags, 0)

        b.f1 = True
        self.assertEqual(b.flags, 1)
        b.f4 = True
        self.assertEqual(b.flags, 5)

        b.f32 = True
        self.assertEqual(b.flags, 37)

    def test_bit_field_instance_flags(self):
        b = Bits()
        self.assertEqual(b.flags, 0)
        self.assertFalse(b.is_sticky)
        self.assertFalse(b.is_favorite)
        self.assertFalse(b.is_minimized)

        b.is_sticky = True
        b.is_minimized = True
        self.assertEqual(b.flags, 5)  # 1 | 4

        self.assertTrue(b.is_sticky)
        self.assertFalse(b.is_favorite)
        self.assertTrue(b.is_minimized)

        b.flags = 3
        self.assertTrue(b.is_sticky)
        self.assertTrue(b.is_favorite)
        self.assertFalse(b.is_minimized)

    def test_bit_field(self):
        b1 = Bits.create(flags=1)
        b2 = Bits.create(flags=2)
        b3 = Bits.create(flags=3)

        query = Bits.select().where(Bits.is_sticky).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id, b3.id])

        query = Bits.select().where(Bits.is_favorite).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b2.id, b3.id])

        # "&" operator does bitwise and for BitField.
        query = Bits.select().where((Bits.flags & 1) == 1).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id, b3.id])

    def test_bigbit_field_instance_data(self):
        b = Bits()
        values_to_set = (1, 11, 63, 31, 55, 48, 100, 99)
        for value in values_to_set:
            b.data.set_bit(value)

        for i in range(128):
            self.assertEqual(b.data.is_set(i), i in values_to_set)

        for i in range(128):
            b.data.clear_bit(i)

        buf = bytes_type(b.data._buffer)
        self.assertEqual(len(buf), 16)

        self.assertEqual(bytes_type(buf), b'\x00' * 16)

    def test_bigbit_zero_idx(self):
        b = Bits()
        b.data.set_bit(0)
        self.assertTrue(b.data.is_set(0))
        b.data.clear_bit(0)
        self.assertFalse(b.data.is_set(0))

    def test_bigbit_field(self):
        b = Bits.create()
        b.data.set_bit(1)
        b.data.set_bit(3)
        b.data.set_bit(5)
        b.save()

        b_db = Bits.get(Bits.id == b.id)
        for x in range(7):
            if x % 2 == 1:
                self.assertTrue(b_db.data.is_set(x))
            else:
                self.assertFalse(b_db.data.is_set(x))


class BlobModel(TestModel):
    data = BlobField()


class TestBlobField(ModelTestCase):
    requires = [BlobModel]

    def test_blob_field(self):
        b = BlobModel.create(data=b'\xff\x01')
        b_db = BlobModel.get(BlobModel.data == b'\xff\x01')
        self.assertEqual(b.id, b_db.id)

        data = b_db.data
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif not isinstance(data, bytes):
            data = bytes(data)
        self.assertEqual(data, b'\xff\x01')

    def test_blob_on_proxy(self):
        db = Proxy()
        class NewBlobModel(Model):
            data = BlobField()
            class Meta:
                database = db

        db_obj = SqliteDatabase(':memory:')
        db.initialize(db_obj)
        self.assertTrue(NewBlobModel.data._constructor is sqlite3.Binary)


class BigModel(TestModel):
    pk = BigAutoField()
    data = TextField()


class TestBigAutoField(ModelTestCase):
    requires = [BigModel]

    def test_big_auto_field(self):
        b1 = BigModel.create(data='b1')
        b2 = BigModel.create(data='b2')

        b1_db = BigModel.get(BigModel.pk == b1.pk)
        b2_db = BigModel.get(BigModel.pk == b2.pk)

        self.assertTrue(b1_db.pk < b2_db.pk)
        self.assertTrue(b1_db.data, 'b1')
        self.assertTrue(b2_db.data, 'b2')


class Item(TestModel):
    price = IntegerField()
    multiplier = FloatField(default=1.)


class Bare(TestModel):
    key = BareField()
    value = BareField(adapt=int, null=True)


class TestFieldValueHandling(ModelTestCase):
    requires = [Item]

    def test_int_float_multi(self):
        i = Item.create(price=10, multiplier=0.75)

        query = (Item
                 .select(Item, (Item.price * Item.multiplier).alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * "t1"."multiplier") AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [i.id])

        i_db = query.get()
        self.assertEqual(i_db.price, 10)
        self.assertEqual(i_db.multiplier, .75)
        self.assertEqual(i_db.total, 7.5)

        # By default, Peewee will use the Price field (integer) converter to
        # coerce the value of it's right-hand operand (converting to 0).
        query = (Item
                 .select(Item, (Item.price * 0.75).alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * ?) AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [0, i.id])

        # We can explicitly pass "False" and the value will not be converted.
        exp = Item.price * Value(0.75, False)
        query = (Item
                 .select(Item, exp.alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * ?) AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [0.75, i.id])

        i_db = query.get()
        self.assertEqual(i_db.price, 10)
        self.assertEqual(i_db.multiplier, .75)
        self.assertEqual(i_db.total, 7.5)

    def test_explicit_cast(self):
        prices = ((10, 1.1), (5, .5))
        for price, multiplier in prices:
            Item.create(price=price, multiplier=multiplier)

        text = 'CHAR' if IS_MYSQL else 'TEXT'

        query = (Item
                 .select(Item.price.cast(text).alias('price_text'),
                         Item.multiplier.cast(text).alias('multiplier_text'))
                 .order_by(Item.id)
                 .dicts())
        self.assertEqual(list(query), [
            {'price_text': '10', 'multiplier_text': '1.1'},
            {'price_text': '5', 'multiplier_text': '0.5'},
        ])

        item = (Item
                .select(Item.price.cast(text).alias('price'),
                        Item.multiplier.cast(text).alias('multiplier'))
                .where(Item.price == 10)
                .get())
        self.assertEqual(item.price, '10')
        self.assertEqual(item.multiplier, '1.1')

    @requires_sqlite
    @requires_models(Bare)
    def test_bare_model_adapt(self):
        b1 = Bare.create(key='k1', value=1)
        b2 = Bare.create(key='k2', value='2')
        b3 = Bare.create(key='k3', value=None)

        b1_db = Bare.get(Bare.id == b1.id)
        self.assertEqual(b1_db.key, 'k1')
        self.assertEqual(b1_db.value, 1)

        b2_db = Bare.get(Bare.id == b2.id)
        self.assertEqual(b2_db.key, 'k2')
        self.assertEqual(b2_db.value, 2)

        b3_db = Bare.get(Bare.id == b3.id)
        self.assertEqual(b3_db.key, 'k3')
        self.assertTrue(b3_db.value is None)


class UUIDModel(TestModel):
    data = UUIDField(null=True)
    bdata = BinaryUUIDField(null=True)


class TestUUIDField(ModelTestCase):
    requires = [UUIDModel]

    def test_uuid_field(self):
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu)

        u_db = UUIDModel.get(UUIDModel.id == u.id)
        self.assertEqual(u_db.data, uu)
        self.assertTrue(u_db.bdata is None)

        u_db2 = UUIDModel.get(UUIDModel.data == uu)
        self.assertEqual(u_db2.id, u.id)

    def test_binary_uuid_field(self):
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu)

        u_db = UUIDModel.get(UUIDModel.id == u.id)
        self.assertEqual(u_db.bdata, uu)
        self.assertTrue(u_db.data is None)

        u_db2 = UUIDModel.get(UUIDModel.bdata == uu)
        self.assertEqual(u_db2.id, u.id)


class ListField(TextField):
    def db_value(self, value):
        return ','.join(value) if value else ''

    def python_value(self, value):
        return value.split(',') if value else []


class Todo(TestModel):
    content = TextField()
    tags = ListField()


class TestCustomField(ModelTestCase):
    requires = [Todo]

    def test_custom_field(self):
        t1 = Todo.create(content='t1', tags=['t1-a', 't1-b'])
        t2 = Todo.create(content='t2', tags=[])

        t1_db = Todo.get(Todo.id == t1.id)
        self.assertEqual(t1_db.tags, ['t1-a', 't1-b'])

        t2_db = Todo.get(Todo.id == t2.id)
        self.assertEqual(t2_db.tags, [])

        t1_db = Todo.get(Todo.tags == AsIs(['t1-a', 't1-b']))
        self.assertEqual(t1_db.id, t1.id)

        t2_db = Todo.get(Todo.tags == AsIs([]))
        self.assertEqual(t2_db.id, t2.id)


class UpperField(TextField):
    def db_value(self, value):
        return fn.UPPER(value)


class UpperModel(TestModel):
    name = UpperField()


class TestSQLFunctionDBValue(ModelTestCase):
    database = get_in_memory_db()
    requires = [UpperModel]

    def test_sql_function_db_value(self):
        # Verify that the db function is applied as part of an INSERT.
        um = UpperModel.create(name='huey')
        um_db = UpperModel.get(UpperModel.id == um.id)
        self.assertEqual(um_db.name, 'HUEY')

        # Verify that the db function is applied as part of an UPDATE.
        um_db.name = 'zaizee'
        um_db.save()

        # Ensure that the name was updated correctly.
        um_db2 = UpperModel.get(UpperModel.id == um.id)
        self.assertEqual(um_db2.name, 'ZAIZEE')

        # Verify that the db function is applied in a WHERE expression.
        um_db3 = UpperModel.get(UpperModel.name == 'zaiZee')
        self.assertEqual(um_db3.id, um.id)

        # If we nest the field in a function, the conversion is not applied.
        expr = fn.SUBSTR(UpperModel.name, 1, 1) == 'z'
        self.assertRaises(UpperModel.DoesNotExist, UpperModel.get, expr)
