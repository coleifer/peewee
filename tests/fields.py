import datetime
from decimal import Decimal as D
from decimal import ROUND_UP

from peewee import *

from .base import db
from .base import ModelTestCase
from .base import TestModel
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
            with self.assertRaises(IntegrityError):
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


class TestDateFields(ModelTestCase):
    requires = [DateModel]

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
            'FROM "phonebook" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?) '
            'ORDER BY "t1"."name"'), [1, 1, 'h'])

        self.assertEqual([pb.name for pb in query], ['hallee', 'huey'])

    def test_field_function(self):
        self._test_field_function(PhoneBook)

    def test_field_function_alias(self):
        self._test_field_function(PhoneBook.alias())
