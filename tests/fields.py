import calendar
import datetime
import sqlite3
import time
import uuid
from decimal import Decimal as D
from decimal import ROUND_UP

from peewee import bytes_type
from peewee import NodeList
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
from .base import requires_mysql
from .base import requires_postgresql
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

    def test_truncate_date(self):
        dm = DateModel.create(
            date_time=datetime.datetime(2001, 2, 3, 4, 5, 6, 7),
            date=datetime.date(2002, 3, 4))

        accum = []
        for p in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            accum.append(DateModel.date_time.truncate(p))
        for p in ('year', 'month', 'day'):
            accum.append(DateModel.date.truncate(p))

        query = DateModel.select(*accum).tuples()
        data = list(query[0])

        # Postgres includes timezone info, so strip that for comparison.
        if IS_POSTGRESQL:
            data = [dt.replace(tzinfo=None) for dt in data]

        self.assertEqual(data, [
            datetime.datetime(2001, 1, 1, 0, 0, 0),
            datetime.datetime(2001, 2, 1, 0, 0, 0),
            datetime.datetime(2001, 2, 3, 0, 0, 0),
            datetime.datetime(2001, 2, 3, 4, 0, 0),
            datetime.datetime(2001, 2, 3, 4, 5, 0),
            datetime.datetime(2001, 2, 3, 4, 5, 6),
            datetime.datetime(2002, 1, 1, 0, 0, 0),
            datetime.datetime(2002, 3, 1, 0, 0, 0),
            datetime.datetime(2002, 3, 4, 0, 0, 0)])

    def test_to_timestamp(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        ts = calendar.timegm(dt.utctimetuple())

        dt2 = datetime.datetime(2019, 1, 3)
        ts2 = calendar.timegm(dt2.utctimetuple())

        DateModel.create(date_time=dt, date=dt2.date())

        query = DateModel.select(
            DateModel.id,
            DateModel.date_time.to_timestamp().alias('dt_ts'),
            DateModel.date.to_timestamp().alias('dt2_ts'))
        obj = query.get()

        self.assertEqual(obj.dt_ts, ts)
        self.assertEqual(obj.dt2_ts, ts2)

        ts3 = ts + 86400
        query = (DateModel.select()
                 .where((DateModel.date_time.to_timestamp() + 86400) < ts3))
        self.assertRaises(DateModel.DoesNotExist, query.get)

        query = (DateModel.select()
                 .where((DateModel.date.to_timestamp() + 86400) > ts3))
        self.assertEqual(query.get().id, obj.id)

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


class TestDeferredForeignKeyResolution(ModelTestCase):
    def test_unresolved_deferred_fk(self):
        class Photo(Model):
            album = DeferredForeignKey('Album', column_name='id_album')
            class Meta:
                database = get_in_memory_db()
        self.assertSQL(Photo.select(), (
            'SELECT "t1"."id", "t1"."id_album" FROM "photo" AS "t1"'), [])

    def test_deferred_foreign_key_resolution(self):
        class Base(Model):
            class Meta:
                database = get_in_memory_db()

        class Photo(Base):
            album = DeferredForeignKey('Album', column_name='id_album',
                                       null=False, backref='pictures')
            alt_album = DeferredForeignKey('Album', column_name='id_Alt_album',
                                           field='alt_id', backref='alt_pix',
                                           null=True)

        class Album(Base):
            name = TextField()
            alt_id = IntegerField(column_name='_Alt_id')

        self.assertTrue(Photo.album.rel_model is Album)
        self.assertTrue(Photo.album.rel_field is Album.id)
        self.assertEqual(Photo.album.column_name, 'id_album')
        self.assertFalse(Photo.album.null)

        self.assertTrue(Photo.alt_album.rel_model is Album)
        self.assertTrue(Photo.alt_album.rel_field is Album.alt_id)
        self.assertEqual(Photo.alt_album.column_name, 'id_Alt_album')
        self.assertTrue(Photo.alt_album.null)

        self.assertSQL(Photo._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "photo" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"id_album" INTEGER NOT NULL, '
            '"id_Alt_album" INTEGER)'), [])

        self.assertSQL(Photo._schema._create_foreign_key(Photo.album), (
            'ALTER TABLE "photo" ADD CONSTRAINT "fk_photo_id_album_refs_album"'
            ' FOREIGN KEY ("id_album") REFERENCES "album" ("id")'))
        self.assertSQL(Photo._schema._create_foreign_key(Photo.alt_album), (
            'ALTER TABLE "photo" ADD CONSTRAINT '
            '"fk_photo_id_Alt_album_refs_album"'
            ' FOREIGN KEY ("id_Alt_album") REFERENCES "album" ("_Alt_id")'))

        self.assertSQL(Photo.select(), (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1"'), [])

        a = Album(id=3, alt_id=4)
        self.assertSQL(a.pictures, (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1" WHERE ("t1"."id_album" = ?)'), [3])
        self.assertSQL(a.alt_pix, (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1" WHERE ("t1"."id_Alt_album" = ?)'), [4])


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

        query = Bits.select().where(~Bits.is_favorite).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id])

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

    def test_blob_db_hook(self):
        sentinel = object()

        class FakeDatabase(Database):
            def get_binary_type(self):
                return sentinel

        class B(Model):
            b1 = BlobField()
            b2 = BlobField()

        B._meta.set_database(FakeDatabase(None))
        self.assertTrue(B.b1._constructor is sentinel)
        self.assertTrue(B.b2._constructor is sentinel)

        alt_db = SqliteDatabase(':memory:')
        with alt_db.bind_ctx([B]):
            # The constructor has been changed.
            self.assertTrue(B.b1._constructor is sqlite3.Binary)
            self.assertTrue(B.b2._constructor is sqlite3.Binary)

        # The constructor has been restored.
        self.assertTrue(B.b1._constructor is sentinel)
        self.assertTrue(B.b2._constructor is sentinel)


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

        # Verify we can use hex string.
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu.hex)
        u_db = UUIDModel.get(UUIDModel.data == uu.hex)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.data, uu)

        # Verify we can use raw binary representation.
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu.bytes)
        u_db = UUIDModel.get(UUIDModel.data == uu.bytes)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.data, uu)

    def test_binary_uuid_field(self):
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu)

        u_db = UUIDModel.get(UUIDModel.id == u.id)
        self.assertEqual(u_db.bdata, uu)
        self.assertTrue(u_db.data is None)

        u_db2 = UUIDModel.get(UUIDModel.bdata == uu)
        self.assertEqual(u_db2.id, u.id)

        # Verify we can use hex string.
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu.hex)
        u_db = UUIDModel.get(UUIDModel.bdata == uu.hex)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.bdata, uu)

        # Verify we can use raw binary representation.
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu.bytes)
        u_db = UUIDModel.get(UUIDModel.bdata == uu.bytes)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.bdata, uu)


class UU1(TestModel):
    id = UUIDField(default=uuid.uuid4, primary_key=True)
    name = TextField()

class UU2(TestModel):
    id = UUIDField(default=uuid.uuid4, primary_key=True)
    u1 = ForeignKeyField(UU1)
    name = TextField()


class TestForeignKeyUUIDField(ModelTestCase):
    requires = [UU1, UU2]

    def test_bulk_insert(self):
        # Create three UU1 instances.
        UU1.insert_many([{UU1.name: name} for name in 'abc'],
                       fields=[UU1.id, UU1.name]).execute()
        ua, ub, uc = UU1.select().order_by(UU1.name)

        # Create several UU2 instances.
        data = (
            ('a1', ua),
            ('b1', ub),
            ('b2', ub),
            ('c1', uc))
        iq = UU2.insert_many([{UU2.name: name, UU2.u1: u} for name, u in data],
                             fields=[UU2.id, UU2.name, UU2.u1])
        iq.execute()

        query = UU2.select().order_by(UU2.name)
        for (name, u1), u2 in zip(data, query):
            self.assertEqual(u2.name, name)
            self.assertEqual(u2.u1.id, u1.id)


class TSModel(TestModel):
    ts_s = TimestampField()
    ts_us = TimestampField(resolution=10 ** 6)
    ts_ms = TimestampField(resolution=3)  # Milliseconds.
    ts_u = TimestampField(null=True, utc=True)


class TSR(TestModel):
    ts_0 = TimestampField(resolution=0)
    ts_1 = TimestampField(resolution=1)
    ts_10 = TimestampField(resolution=10)
    ts_2 = TimestampField(resolution=2)


class TestTimestampField(ModelTestCase):
    requires = [TSModel]

    @requires_models(TSR)
    def test_timestamp_field_resolutions(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7).replace(microsecond=123456)
        ts = TSR.create(ts_0=dt, ts_1=dt, ts_10=dt, ts_2=dt)
        ts_db = TSR[ts.id]

        # Zero and one are both treated as "seconds" resolution.
        self.assertEqual(ts_db.ts_0, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_1, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_10, dt.replace(microsecond=100000))
        self.assertEqual(ts_db.ts_2, dt.replace(microsecond=120000))

    def test_timestamp_field(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7)
        dt = dt.replace(microsecond=31337)  # us=031_337, ms=031.
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt)
        ts_db = TSModel.get(TSModel.id == ts.id)
        self.assertEqual(ts_db.ts_s, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_ms, dt.replace(microsecond=31000))
        self.assertEqual(ts_db.ts_us, dt)
        self.assertEqual(ts_db.ts_u, dt.replace(microsecond=0))

        self.assertEqual(TSModel.get(TSModel.ts_s == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_ms == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_us == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_u == dt).id, ts.id)

    def test_timestamp_field_math(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5, 31337)
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt)

        # Although these fields use different scales for storing the
        # timestamps, adding "1" has the effect of adding a single second -
        # the value will be multiplied by the correct scale via the converter.
        TSModel.update(
            ts_s=TSModel.ts_s + 1,
            ts_us=TSModel.ts_us + 1,
            ts_ms=TSModel.ts_ms + 1).execute()

        ts_db = TSModel.get(TSModel.id == ts.id)
        dt2 = dt + datetime.timedelta(seconds=1)
        self.assertEqual(ts_db.ts_s, dt2.replace(microsecond=0))
        self.assertEqual(ts_db.ts_us, dt2)
        self.assertEqual(ts_db.ts_ms, dt2.replace(microsecond=31000))

    def test_timestamp_field_value_as_ts(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7, 31337)
        unix_ts = time.mktime(dt.timetuple()) + 0.031337
        ts = TSModel.create(ts_s=unix_ts, ts_us=unix_ts, ts_ms=unix_ts,
                            ts_u=unix_ts)

        # Fetch from the DB and validate the values were stored correctly.
        ts_db = TSModel[ts.id]
        self.assertEqual(ts_db.ts_s, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_ms, dt.replace(microsecond=31000))
        self.assertEqual(ts_db.ts_us, dt)

        utc_dt = TimestampField().local_to_utc(dt)
        self.assertEqual(ts_db.ts_u, utc_dt)

        # Verify we can query using a timestamp.
        self.assertEqual(TSModel.get(TSModel.ts_s == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_ms == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_us == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_u == unix_ts).id, ts.id)

    def test_timestamp_utc_vs_localtime(self):
        local_field = TimestampField()
        utc_field = TimestampField(utc=True)

        dt = datetime.datetime(2019, 1, 1, 12)
        unix_ts = int(local_field.get_timestamp(dt))
        utc_ts = int(utc_field.get_timestamp(dt))

        # Local timestamp is unmodified. Verify that when utc=True, the
        # timestamp is converted from local time to UTC.
        self.assertEqual(local_field.db_value(dt), unix_ts)
        self.assertEqual(utc_field.db_value(dt), utc_ts)

        self.assertEqual(local_field.python_value(unix_ts), dt)
        self.assertEqual(utc_field.python_value(utc_ts), dt)

        # Convert back-and-forth several times.
        dbv, pyv = local_field.db_value, local_field.python_value
        self.assertEqual(pyv(dbv(pyv(dbv(dt)))), dt)

        dbv, pyv = utc_field.db_value, utc_field.python_value
        self.assertEqual(pyv(dbv(pyv(dbv(dt)))), dt)

    def test_timestamp_field_parts(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        dt_utc = TimestampField().local_to_utc(dt)
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt_utc)

        fields = (TSModel.ts_s, TSModel.ts_us, TSModel.ts_ms, TSModel.ts_u)
        attrs = ('year', 'month', 'day', 'hour', 'minute', 'second')
        selection = []
        for field in fields:
            for attr in attrs:
                selection.append(getattr(field, attr))

        row = TSModel.select(*selection).tuples()[0]

        # First ensure that all 3 fields are returning the same data.
        ts_s, ts_us, ts_ms, ts_u = row[:6], row[6:12], row[12:18], row[18:]
        self.assertEqual(ts_s, ts_us)
        self.assertEqual(ts_s, ts_ms)
        self.assertEqual(ts_s, ts_u)

        # Now validate that the data is correct. We will receive the data back
        # as a UTC unix timestamp, however!
        y, m, d, H, M, S = ts_s
        self.assertEqual(y, 2019)
        self.assertEqual(m, 1)
        self.assertEqual(d, 2)
        self.assertEqual(H, dt_utc.hour)
        self.assertEqual(M, 4)
        self.assertEqual(S, 5)

    def test_timestamp_field_from_ts(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        dt_utc = TimestampField().local_to_utc(dt)

        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt_utc)
        query = TSModel.select(
            TSModel.ts_s.from_timestamp().alias('dt_s'),
            TSModel.ts_us.from_timestamp().alias('dt_us'),
            TSModel.ts_ms.from_timestamp().alias('dt_ms'),
            TSModel.ts_u.from_timestamp().alias('dt_u'))

        # Get row and unpack into variables corresponding to the fields.
        row = query.tuples()[0]
        dt_s, dt_us, dt_ms, dt_u = row

        # Ensure the timestamp values for all 4 fields are the same.
        self.assertEqual(dt_s, dt_us)
        self.assertEqual(dt_s, dt_ms)
        self.assertEqual(dt_s, dt_u)
        if IS_SQLITE:
            expected = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
            self.assertEqual(dt_s, expected)
        elif IS_POSTGRESQL:
            # Postgres returns an aware UTC datetime. Strip this to compare
            # against our naive UTC datetime.
            self.assertEqual(dt_s.replace(tzinfo=None), dt_utc)

    def test_invalid_resolution(self):
        self.assertRaises(ValueError, TimestampField, resolution=7)
        self.assertRaises(ValueError, TimestampField, resolution=20)
        self.assertRaises(ValueError, TimestampField, resolution=10**7)


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


class Schedule(TestModel):
    interval = IntegerField()

class Task(TestModel):
    schedule = ForeignKeyField(Schedule)
    name = TextField()
    last_run = DateTimeField()


class TestDateTimeMath(ModelTestCase):
    offset_to_names = (
        (-10, ()),
        (5, ('s1',)),
        (10, ('s1', 's10')),
        (11, ('s1', 's10')),
        (60, ('s1', 's10', 's60')),
        (61, ('s1', 's10', 's60')))
    requires = [Schedule, Task]

    def setUp(self):
        super(TestDateTimeMath, self).setUp()
        with self.database.atomic():
            s1 = Schedule.create(interval=1)
            s10 = Schedule.create(interval=10)
            s60 = Schedule.create(interval=60)

            self.dt = datetime.datetime(2019, 1, 1, 12)
            for s, n in ((s1, 's1'), (s10, 's10'), (s60, 's60')):
                Task.create(schedule=s, name=n, last_run=self.dt)

    def _do_test_date_time_math(self, next_occurrence_expression):
        for offset, names in self.offset_to_names:
            dt = Value(self.dt + datetime.timedelta(seconds=offset))
            query = (Task
                     .select(Task, Schedule)
                     .join(Schedule)
                     .where(dt >= next_occurrence_expression)
                     .order_by(Schedule.interval))
            tnames = [task.name for task in query]
            self.assertEqual(list(names), tnames)

    @requires_postgresql
    def test_date_time_math_pg(self):
        second = SQL("INTERVAL '1 second'")
        next_occurrence = Task.last_run + (Schedule.interval * second)
        self._do_test_date_time_math(next_occurrence)

    @requires_sqlite
    def test_date_time_math_sqlite(self):
        # Convert to a timestamp, add the scheduled seconds, then convert back
        # to a datetime string for comparison with the last occurrence.
        next_ts = Task.last_run.to_timestamp() + Schedule.interval
        next_occurrence = fn.datetime(next_ts, 'unixepoch')
        self._do_test_date_time_math(next_occurrence)

    @requires_mysql
    def test_date_time_math_mysql(self):
        nl = NodeList((SQL('INTERVAL'), Schedule.interval, SQL('SECOND')))
        next_occurrence = fn.date_add(Task.last_run, nl)
        self._do_test_date_time_math(next_occurrence)


class NQ(TestModel):
    name = TextField()

class NQItem(TestModel):
    nq = ForeignKeyField(NQ, backref='items')
    nq_null = ForeignKeyField(NQ, backref='null_items', null=True)
    nq_lazy = ForeignKeyField(NQ, lazy_load=False, backref='lazy_items')
    nq_lazy_null = ForeignKeyField(NQ, lazy_load=False,
                                   backref='lazy_null_items', null=True)


class TestForeignKeyLazyLoad(ModelTestCase):
    requires = [NQ, NQItem]

    def setUp(self):
        super(TestForeignKeyLazyLoad, self).setUp()
        with self.database.atomic():
            a1, a2, a3, a4 = [NQ.create(name='a%s' % i) for i in range(1, 5)]
            ai = NQItem.create(nq=a1, nq_null=a2, nq_lazy=a3, nq_lazy_null=a4)

            b = NQ.create(name='b')
            bi = NQItem.create(nq=b, nq_lazy=b)

    def test_foreign_key_lazy_load(self):
        a1, a2, a3, a4 = (NQ.select()
                          .where(NQ.name.startswith('a'))
                          .order_by(NQ.name))
        b = NQ.get(NQ.name == 'b')
        ai = NQItem.get(NQItem.nq_id == a1.id)
        bi = NQItem.get(NQItem.nq_id == b.id)

        # Accessing the lazy foreign-key fields will not result in any queries
        # being executed.
        with self.assertQueryCount(0):
            self.assertEqual(ai.nq_lazy, a3.id)
            self.assertEqual(ai.nq_lazy_null, a4.id)
            self.assertEqual(bi.nq_lazy, b.id)
            self.assertTrue(bi.nq_lazy_null is None)
            self.assertTrue(bi.nq_null is None)

        # Accessing the regular foreign-key fields uses a query to get the
        # related model instance.
        with self.assertQueryCount(2):
            self.assertEqual(ai.nq.id, a1.id)
            self.assertEqual(ai.nq_null.id, a2.id)

        with self.assertQueryCount(1):
            self.assertEqual(bi.nq.id, b.id)

    def test_fk_lazy_select_related(self):
        NA, NB, NC, ND = [NQ.alias(a) for a in ('na', 'nb', 'nc', 'nd')]
        LO = JOIN.LEFT_OUTER
        query = (NQItem.select(NQItem, NA, NB, NC, ND)
                 .join_from(NQItem, NA, LO, on=NQItem.nq)
                 .join_from(NQItem, NB, LO, on=NQItem.nq_null)
                 .join_from(NQItem, NC, LO, on=NQItem.nq_lazy)
                 .join_from(NQItem, ND, LO, on=NQItem.nq_lazy_null)
                 .order_by(NQItem.id))

        # If we explicitly / eagerly select lazy foreign-key models, they
        # behave just like regular foreign keys.
        with self.assertQueryCount(1):
            ai, bi = [ni for ni in query]
            self.assertEqual(ai.nq.name, 'a1')
            self.assertEqual(ai.nq_null.name, 'a2')
            self.assertEqual(ai.nq_lazy.name, 'a3')
            self.assertEqual(ai.nq_lazy_null.name, 'a4')

            self.assertEqual(bi.nq.name, 'b')
            self.assertEqual(bi.nq_lazy.name, 'b')
            self.assertTrue(bi.nq_null is None)
            self.assertTrue(bi.nq_lazy_null is None)


class SM(TestModel):
    text_field = TextField()
    char_field = CharField()


class TestStringFields(ModelTestCase):
    requires = [SM]

    def test_string_fields(self):
        bdata = b'b1'
        udata = b'u1'.decode('utf8')

        sb = SM.create(text_field=bdata, char_field=bdata)
        su = SM.create(text_field=udata, char_field=udata)

        sb_db = SM.get(SM.id == sb.id)
        self.assertEqual(sb_db.text_field, 'b1')
        self.assertEqual(sb_db.char_field, 'b1')

        su_db = SM.get(SM.id == su.id)
        self.assertEqual(su_db.text_field, 'u1')
        self.assertEqual(su_db.char_field, 'u1')

        bvals = (b'b1', u'b1')
        uvals = (b'u1', u'u1')

        for field in (SM.text_field, SM.char_field):
            for bval in bvals:
                sb_db = SM.get(field == bval)
                self.assertEqual(sb.id, sb_db.id)

            for uval in uvals:
                sb_db = SM.get(field == uval)
                self.assertEqual(su.id, su_db.id)


class InvalidTypes(TestModel):
    tfield = TextField()
    ifield = IntegerField()
    ffield = FloatField()


class TestSqliteInvalidDataTypes(ModelTestCase):
    database = get_in_memory_db()
    requires = [InvalidTypes]

    def test_invalid_data_types(self):
        it = InvalidTypes.create(tfield=100, ifield='five', ffield='pi')
        it_db1 = InvalidTypes.get(InvalidTypes.tfield == 100)
        it_db2 = InvalidTypes.get(InvalidTypes.ifield == 'five')
        it_db3 = InvalidTypes.get(InvalidTypes.ffield == 'pi')
        self.assertTrue(it.id == it_db1.id == it_db2.id == it_db3.id)

        self.assertEqual(it_db1.tfield, '100')
        self.assertEqual(it_db1.ifield, 'five')
        self.assertEqual(it_db1.ffield, 'pi')
