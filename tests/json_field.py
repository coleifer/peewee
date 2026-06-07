import json

from peewee import *
from peewee import sqlite3

from playhouse.json_field import JSONField
from playhouse.json_field import JSONPath

from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import skip_if
from .base import skip_unless


IS_SQLITE_38 = IS_SQLITE and sqlite3.sqlite_version_info >= (3, 38)
SKIP_PATHS = IS_SQLITE and not IS_SQLITE_38


class JM(TestModel):
    data = JSONField(null=True)


class TestStorageRoundTrip(ModelTestCase):
    requires = [JM]

    def _round_trip(self, value):
        JM.delete().execute()
        JM.create(data=value)
        return JM.select().get().data

    def assertRoundTrip(self, value):
        got = self._round_trip(value)
        self.assertEqual(got, value)
        if value is not None:
            self.assertEqual(type(got), type(value))

    def test_strings(self):
        cases = [
            '',
            'hello',
            "with 'quotes'",
            'with "doubles"',
            'with\nnewlines\ttabs',
            'with\\backslashes',
            'unicode héllo \U0001f30d 漢字', ' ' * 10,
            '{"k": 1}',
            'x' * 10000,
        ]
        for v in cases:
            self.assertRoundTrip(v)

    def test_ints(self):
        for v in (0, 1, -1, 2**31 - 1, -(2**31), 2**53 - 1):
            self.assertRoundTrip(v)

    def test_floats(self):
        for v in (0.0, 1.5, -1.5, 1e10, 1e-10):
            self.assertRoundTrip(v)
        if IS_SQLITE:
            self.assertRoundTrip(float('inf'))
            self.assertRoundTrip(float('-inf'))

    def test_bools(self):
        self.assertIs(self._round_trip(True), True)
        self.assertIs(self._round_trip(False), False)

    def test_sql_null(self):
        JM.delete().execute()
        JM.create(data=None)
        self.assertIsNone(JM.select().first().data)

    def test_containers(self):
        self.assertRoundTrip([])
        self.assertRoundTrip({})
        self.assertRoundTrip([1, 'a', True, None, 1.5])
        self.assertRoundTrip({'a': 1, 'b': 'two', 'c': True, 'd': None})

    def test_deep(self):
        self.assertRoundTrip({'a': {'b': {'c': {'d': 1}}}})
        self.assertRoundTrip({'a': [{'b': [{'c': 1}]}]})

    def test_special_keys(self):
        self.assertRoundTrip({'a.b': 1})
        self.assertRoundTrip({'k"q': 1})
        self.assertRoundTrip({'': 'empty key'})
        self.assertRoundTrip({'漢字': 'unicode key'})

    def test_json_null_inside(self):
        self.assertRoundTrip({'k': None})
        self.assertRoundTrip([None])


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestPathExtract(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestPathExtract, self).setUp()
        JM.create(data={
            'name': 'huey',
            'age': 14,
            'active': True,
            'approval_rating': 4.5,
            'tags': ['cat', 'white', 'fluffy'],
            'profile': {'location': 'top city',
                        'social': {'fb': 'huey.cat'}},
            'nullval': None,
            'matrix': [[1, 2], [3, 4], [5, 6]],
            'a.b': 'dotted key',
        })

    def _val(self, *keys, as_text=False):
        path = JM.data.path(*keys)
        if as_text:
            path = path.as_text()
        return JM.select(path).scalar()

    def test_scalars(self):
        self.assertEqual(self._val('name'), 'huey')
        self.assertEqual(self._val('age'), 14)
        self.assertIs(self._val('active'), True)
        self.assertEqual(self._val('approval_rating'), 4.5)
        self.assertIsNone(self._val('nullval'))

    def test_containers(self):
        self.assertEqual(self._val('tags'), ['cat', 'white', 'fluffy'])
        self.assertEqual(self._val('profile'), {
            'location': 'top city',
            'social': {'fb': 'huey.cat'}})

    def test_chain(self):
        self.assertEqual(self._val('profile', 'location'), 'top city')
        self.assertEqual(self._val('profile', 'social', 'fb'), 'huey.cat')

    def test_bracket(self):
        self.assertEqual(JM.select(JM.data['tags'][0]).scalar(), 'cat')
        self.assertEqual(JM.select(JM.data['tags'][2]).scalar(), 'fluffy')
        self.assertEqual(JM.select(JM.data['matrix'][1][0]).scalar(), 3)

    @skip_if(IS_MYSQL)
    def test_negative_index(self):
        self.assertEqual(JM.select(JM.data['tags'][-1]).scalar(), 'fluffy')
        self.assertEqual(JM.select(JM.data['matrix'][-1][-1]).scalar(), 6)

    def test_special_char_key(self):
        self.assertEqual(self._val('a.b'), 'dotted key')

    def test_as_text(self):
        self.assertEqual(self._val('name', as_text=True), 'huey')
        self.assertEqual(int(self._val('age', as_text=True)), 14)
        self.assertIn(self._val('tags', as_text=True), (
            '["cat","white","fluffy"]',
            '["cat", "white", "fluffy"]'))

    def test_path_equiv(self):
        v1 = JM.select(JM.data.path('profile', 'city')).scalar()
        v2 = JM.select(JM.data['profile']['city']).scalar()
        self.assertEqual(v1, v2)

    def test_empty_path(self):
        v = JM.select(JM.data.path()).scalar()
        self.assertEqual(v['name'], 'huey')


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestEquality(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestEquality, self).setUp()
        JM.create(data={'k': 'v', 'n': 5, 'b': True})
        JM.create(data={'k': 'other', 'n': 10})
        JM.create(data=None)

    def test_root_eq(self):
        q = JM.select().where(JM.data == {'k': 'v', 'n': 5, 'b': True})
        # SQLite/MySQL/MariaDB whole-doc eq is byte compare (order-sensitive).
        # All backends here produce the document in the same key order on
        # both sides, so this matches.
        self.assertEqual(q.count(), 1)

    def test_root_eq_none(self):
        self.assertEqual(JM.select().where(JM.data == None).count(), 1)

    def test_root_ne_none(self):
        self.assertEqual(JM.select().where(JM.data != None).count(), 2)

    def test_path_eq_string(self):
        q = JM.select().where(JM.data['k'] == 'v')
        self.assertEqual(q.count(), 1)

    def test_path_eq_int(self):
        # Works on PG (jsonb structural), MySQL (JSON-typed compare), and
        # SQLite (canonical text '5' == json('5')). Confirms the f29578e4
        # critic's "int eq fails" complaint from old peewee is fixed here.
        q = JM.select().where(JM.data['n'] == 5)
        self.assertEqual(q.count(), 1)

    def test_path_eq_bool(self):
        q = JM.select().where(JM.data['b'] == True)
        self.assertEqual(q.count(), 1)

    def test_path_eq_none_matches_missing(self):
        # n is missing on the 'data=None' row and on the {'k':'other','n':10}
        # row — wait, n is present in row 2. So only row 3 (data=None) matches.
        q = JM.select().where(JM.data['n'] == None)
        self.assertEqual(q.count(), 1)

    def test_path_eq_none_matches_missing_key(self):
        # 'nope' is missing in every row. extract_text → SQL NULL → match all.
        q = JM.select().where(JM.data['nope'] == None)
        self.assertEqual(q.count(), 3)

    @skip_if(IS_MYSQL, 'json_unquote flaky on MariaDB and older MySQL')
    def test_path_eq_none_matches_json_null(self):
        JM.delete().execute()
        JM.create(data={'k': None})
        self.assertEqual(JM.select().where(JM.data['k'] == None).count(), 1)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestTypedCasts(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestTypedCasts, self).setUp()
        JM.create(data={'count': 1, 'name': 'Alice'})
        JM.create(data={'count': 50, 'name': 'Bob'})
        JM.create(data={'count': 100, 'name': 'Charlie'})

    def test_as_int_gt(self):
        q = JM.select().where(JM.data['count'].as_int() > 10)
        self.assertEqual(q.count(), 2)

    def test_as_int_between(self):
        q = JM.select().where(JM.data['count'].as_int().between(40, 60))
        self.assertEqual(q.count(), 1)

    def test_as_int_eq(self):
        q = JM.select().where(JM.data['count'].as_int() == 50)
        self.assertEqual(q.count(), 1)

    def test_as_int_order(self):
        rows = list(JM.select(JM.data['count'].as_int().alias('c'))
                    .order_by(JM.data['count'].as_int()))
        self.assertEqual([r.c for r in rows], [1, 50, 100])

    def test_as_float(self):
        JM.delete().execute()
        JM.create(data={'r': 1.5})
        JM.create(data={'r': 3.5})
        q = JM.select().where(JM.data['r'].as_float() > 2.0)
        self.assertEqual(q.count(), 1)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestTextMode(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestTextMode, self).setUp()
        JM.create(data={'name': 'Alice'})
        JM.create(data={'name': 'Bob'})
        JM.create(data={'name': 'Charlie'})

    def test_as_text_eq(self):
        q = JM.select().where(JM.data['name'].as_text() == 'Alice')
        self.assertEqual(q.count(), 1)

    def test_ilike(self):
        # like maps to GLOB on SQLite; ilike maps to LIKE everywhere.
        q = JM.select().where(JM.data['name'].ilike('A%'))
        self.assertEqual(q.count(), 1)

    def test_startswith(self):
        q = JM.select().where(JM.data['name'].startswith('A'))
        self.assertEqual(q.count(), 1)

    def test_endswith(self):
        q = JM.select().where(JM.data['name'].endswith('e'))
        self.assertEqual(q.count(), 2)

    def test_contains_substring(self):
        q = JM.select().where(JM.data['name'].contains('li'))
        self.assertEqual(q.count(), 2)

    def test_in_canonicalized(self):
        # in_ canonicalizes RHS — works across backends without auto-text.
        q = JM.select().where(JM.data['name'].in_(['Alice', 'Bob']))
        self.assertEqual(q.count(), 2)

    def test_in_text_mode(self):
        q = (JM.select()
             .where(JM.data['name'].as_text().in_(['Alice', 'Bob'])))
        self.assertEqual(q.count(), 2)


class TestReadModifyWrite(ModelTestCase):
    requires = [JM]

    def test_dict_mutation(self):
        JM.create(data={'k': 'v'})
        m = JM.select().first()
        m.data['k'] = 'updated'
        m.data['new'] = 1
        m.save()
        self.assertEqual(JM.select().first().data,
                         {'k': 'updated', 'new': 1})

    def test_list_mutation(self):
        JM.create(data={'tags': ['a', 'b']})
        m = JM.select().first()
        m.data['tags'].append('c')
        m.save()
        self.assertEqual(JM.select().first().data['tags'], ['a', 'b', 'c'])

    def test_overwrite(self):
        JM.create(data={'old': 1})
        m = JM.select().first()
        JM.update(data={'new': 2}).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'new': 2})


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestAtomicViaFn(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestAtomicViaFn, self).setUp()
        JM.create(data={'a': 1, 'b': 2})

    def test_atomic_set(self):
        m = JM.select().first()
        if IS_POSTGRESQL:
            atomic = fn.jsonb_set(JM.data, '{a}', Value('99'))
        elif IS_MYSQL:
            atomic = fn.JSON_SET(JM.data, '$.a', 99)
        else:
            atomic = fn.json_set(JM.data, '$.a', 99)
        JM.update(data=atomic).where(JM.id == m.id).execute()
        got = JM.get_by_id(m.id).data
        self.assertEqual(got['a'], 99)
        self.assertEqual(got['b'], 2)


class TestCustomDumps(ModelTestCase):
    requires = []

    def test_decimal_dumps(self):
        from decimal import Decimal

        def custom_dumps(value):
            def _default(o):
                if isinstance(o, Decimal):
                    return str(o)
                raise TypeError
            return json.dumps(value, default=_default)

        class M(TestModel):
            data = JSONField(null=True, dumps=custom_dumps)

        M._meta.database = db
        M.create_table()
        try:
            M.create(data={'price': Decimal('19.99')})
            got = M.select().first().data
            self.assertEqual(got, {'price': '19.99'})
        finally:
            M.drop_table()


@skip_if(not IS_POSTGRESQL, 'PG-only: cast_for_case is psycopg-specific')
class TestPostgresBulkUpdate(ModelTestCase):
    # bulk_update's CASE-WHEN branch needs an explicit jsonb cast so psycopg
    # can infer the parameter type. The helper provides cast_for_case().
    requires = [JM]

    def test_bulk_update(self):
        a = JM.create(data={'v': 1})
        b = JM.create(data={'v': 2})
        a.data = {'v': 10}
        b.data = {'v': 20}
        JM.bulk_update([a, b], fields=[JM.data])
        self.assertEqual(JM.get_by_id(a.id).data, {'v': 10})
        self.assertEqual(JM.get_by_id(b.id).data, {'v': 20})
