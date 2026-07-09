import json

from peewee import *
from peewee import sqlite3

from .base import IS_CRDB
from .base import IS_MARIADB
from .base import IS_MYSQL
from .base import IS_ORACLE_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import BaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import skip_if
from .base import skip_unless


IS_SQLITE_38 = IS_SQLITE and sqlite3.sqlite_version_info >= (3, 38)
SKIP_PATHS = IS_SQLITE and not IS_SQLITE_38

# CockroachDB rides PostgresqlJSONMethods (and psycopg), so it gets the
# postgres-flavored behaviors and SQL shapes in these tests.
IS_PG_JSON = IS_POSTGRESQL or IS_CRDB


class JM(TestModel):
    data = JSONField(null=True)
    ident = TextField(null=True)


class TM(TestModel):
    text = TextField()


class TestValueMatrix(ModelTestCase):
    # For each representative value: store it, read it back (assert value AND
    # type), then look it up via WHERE data == value (assert match).
    # Combined matrix catches the cross-cut bug where storage works but
    # equality doesn't (or vice versa).
    requires = [JM]

    VALUES = [
        # Strings.
        ('str_empty',          ''),
        ('str_plain',          'hello'),
        ('str_single_quotes',  "with 'single' quotes"),
        ('str_double_quotes',  'with "double" quotes'),
        ('str_specials',       'newlines\nand\ttabs\\and\\backslashes'),
        ('str_unicode',        'unicode héllo ☃ 漢字'),
        ('str_emoji',          'emoji \U0001f30d'),  # Supplementary plane.
        ('str_json_like',      '{"k": 1}'),  # must NOT auto-parse
        ('str_long',           'x' * 10000),
        # Numbers.
        ('int_zero',           0),
        ('int_one',            1),
        ('int_negative',       -1),
        ('int_max_32',         2**31 - 1),
        ('int_min_32',         -(2**31)),
        ('int_max_safe',       2**53 - 1),
        ('float_zero',         0.0),
        ('float_positive',     1.5),
        ('float_negative',     -1.5),
        ('float_large',        1e10),
        ('float_small',        1e-10),
        # Booleans.
        ('bool_true',          True),
        ('bool_false',         False),
        # Containers.
        ('list_empty',         []),
        ('dict_empty',         {}),
        ('list_ints',          [1, 2, 3]),
        ('list_strs',          ['a', 'b', 'c']),
        ('list_mixed',         [1, 'a', True, None, 1.5]),
        ('list_nested',        [[1, 2], [3, 4]]),
        ('dict_simple',        {'a': 1}),
        ('dict_mixed',         {'a': 1, 'b': 'two', 'c': True, 'd': None}),
        ('dict_deep',          {'a': {'b': {'c': {'d': 1}}}}),
        # Special keys.
        ('dict_dotted_key',    {'a.b': 1}),
        ('dict_quoted_key',    {'k"q\\x': 1}),
        ('dict_empty_key',     {'': 'empty key'}),
        ('dict_unicode_key',   {'漢字': 'unicode key'}),
        # JSON null inside a container (distinct from column SQL NULL).
        ('json_null_in_dict',  {'k': None}),
        ('json_null_in_list',  [None]),
        # Column SQL NULL.
        ('sql_null',           None),
    ]

    def _check_storage(self, label, value):
        JM.delete().execute()
        JM.create(data=value, ident=label)
        jm_db = JM.select().where(JM.ident == label).get()
        stored = jm_db.data
        self.assertEqual(stored, value,
            '[%s] storage round-trip value mismatch' % label)
        self.assertIs(type(stored), type(value),
            '[%s] storage round-trip type mismatch: %s vs %s' % (
                label, type(stored).__name__, type(value).__name__))

    def _check_filter(self, label, value):
        # Find by equality with the same value.
        rows = list(JM.select().where(JM.data == value))
        self.assertEqual(len(rows), 1,
            '[%s] WHERE data == value did not match the stored row' % label)
        self.assertEqual(rows[0].data, value, '[%s] matched-row data drift' % label)
        self.assertEqual(rows[0].ident, label)

    def test_value_matrix(self):
        for label, value in self.VALUES:
            if label == 'str_emoji' and IS_ORACLE_MYSQL:
                # MySQL mangles supplementary-plane chars unless connected
                # w/charset=utf8mb4.
                continue
            with self.subTest(label=label):
                self._check_storage(label, value)
                self._check_filter(label, value)

    def test_sqlite_float_infinity(self):
        # SQLite's JSON1 tolerates non-finite floats; PG and MySQL reject them
        # via the dumps step (json.dumps default allow_nan=True but the driver
        # rejects them at parse time).
        if not IS_SQLITE:
            self.skipTest('SQLite-only: infinity through json1')
        for v in (float('inf'), float('-inf')):
            JM.delete().execute()
            JM.create(data=v)
            self.assertEqual(JM.select().get().data, v)


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
        self.assertEqual(self._val('profile', 'social'), {'fb': 'huey.cat'})

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

    def test_dicts_tuples(self):
        # Path converters apply in the non-model row wrappers, too.
        q = JM.select(JM.data['name'].alias('n'),
                      JM.data['matrix'][0].alias('m'))
        self.assertEqual(list(q.dicts()), [{'n': 'huey', 'm': [1, 2]}])
        self.assertEqual(list(q.tuples()), [('huey', [1, 2])])


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
        self.assertEqual(q.count(), 1)

    def test_root_eq_none(self):
        self.assertEqual(JM.select().where(JM.data == None).count(), 1)

    def test_root_ne_none(self):
        self.assertEqual(JM.select().where(JM.data != None).count(), 2)

    def test_path_eq_string(self):
        q = JM.select().where(JM.data['k'] == 'v')
        self.assertEqual(q.count(), 1)

    def test_path_eq_int(self):
        q = JM.select().where(JM.data['n'] == 5)
        self.assertEqual(q.count(), 1)

    def test_path_eq_bool(self):
        q = JM.select().where(JM.data['b'] == True)
        self.assertEqual(q.count(), 1)

    def test_path_in_canonicalized(self):
        q = JM.select().where(JM.data['k'].in_(['v', 'other']))
        self.assertEqual(q.count(), 2)

        q = JM.select().where(JM.data['k'].in_(['v', 'xyz']))
        self.assertEqual(q.count(), 1)

    def test_path_in_subquery(self):
        sub = JM.select(JM.data['k'].as_text()).where(JM.data['n'] == 5)
        q = JM.select().where(JM.data['k'].as_text().in_(sub))
        self.assertEqual(q.count(), 1)

        q = JM.select().where(JM.data['k'].as_text().not_in(sub))
        self.assertEqual(q.count(), 1)

        sub = JM.select(JM.data['k']).where(JM.data['n'] == 5)
        q = JM.select().where(JM.data['k'].in_(sub))
        self.assertEqual(q.count(), 1)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestContainerEquality(ModelTestCase):
    requires = [JM]

    def test_path_eq_dict(self):
        JM.create(data={'k': {'a': 1, 'b': [1, 2]}}, ident='t')
        JM.create(data={'k': {'a': 2}})
        q = JM.select().where(JM.data['k'] == {'a': 1, 'b': [1, 2]})
        self.assertEqual([r.ident for r in q], ['t'])

    def test_path_eq_list(self):
        JM.create(data={'tags': ['x', 'y']}, ident='t')
        JM.create(data={'tags': ['x']})
        q = JM.select().where(JM.data['tags'] == ['x', 'y'])
        self.assertEqual([r.ident for r in q], ['t'])

    def test_nested_path_eq_dict(self):
        JM.create(data={'a': {'b': {'c': 1, 'd': [1, 2]}}}, ident='t')
        q = JM.select().where(JM.data['a']['b'] == {'c': 1, 'd': [1, 2]})
        self.assertEqual([r.ident for r in q], ['t'])

    def test_path_eq_after_mutation(self):
        # Mutation ops rewrite the document server-side, so the stored text
        # no longer carries the original dumps() formatting - equality must
        # not depend on it surviving (MariaDB byte-compares text).
        JM.create(data={'k': 'placeholder'}, ident='t')
        JM.update(data=JM.data['k'].set({'a': 1, 'b': [2, 3]})).execute()
        q = JM.select().where(JM.data['k'] == {'a': 1, 'b': [2, 3]})
        self.assertEqual([r.ident for r in q], ['t'])

    def test_path_in_containers(self):
        JM.create(data={'k': {'a': 1}}, ident='t1')
        JM.create(data={'k': {'a': 2}}, ident='t2')
        JM.create(data={'k': {'a': 3}})
        q = (JM.select()
             .where(JM.data['k'].in_([{'a': 1}, {'a': 2}]))
             .order_by(JM.ident))
        self.assertEqual([r.ident for r in q], ['t1', 't2'])


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
        if IS_PG_JSON:
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


class TestCustomLoads(ModelTestCase):
    requires = []

    def test_custom_loads(self):
        def custom_loads(s):
            return json.loads(s, parse_int=lambda v: int(v) * 100)

        class ML(TestModel):
            data = JSONField(null=True, loads=custom_loads)

        ML._meta.database = db
        ML.create_table()
        try:
            ML.create(data={'n': 5})
            got = ML.select().first().data
            if IS_PG_JSON:
                # psycopg deserializes json values itself; a custom loads
                # is not applied (see docs).
                self.assertEqual(got, {'n': 5})
            else:
                self.assertEqual(got, {'n': 500})
        finally:
            ML.drop_table()


class TestDeferredDatabase(ModelTestCase):
    requires = []

    def test_proxy_initialize(self):
        proxy = Proxy()

        class PM(TestModel):
            data = JSONField(null=True)
            class Meta:
                database = proxy

        # No helper is configured until the proxy is initialized.
        self.assertIsNone(PM.data._helper)
        proxy.initialize(db)
        self.assertIsNotNone(PM.data._helper)

        PM.create_table()
        try:
            PM.create(data={'k': [1, 2]})
            self.assertEqual(PM.select().first().data, {'k': [1, 2]})
        finally:
            PM.drop_table()


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestInheritedJSONField(ModelTestCase):
    requires = []

    def test_inherit_json_field(self):
        # JSONField stores a db-specific helper instance w/a db ref. Attempting
        # to deepcopy (during inheritance) travels the graph down to the
        # database instance's locks and connection local, which failed.
        class JIBase(TestModel):
            data = JSONField(null=True)

        class JIChild(JIBase):
            extra = JSONField(null=True)

        # The inherited field is an independent copy, re-bound to the child.
        self.assertIsNot(JIChild.data, JIBase.data)
        self.assertIsNotNone(JIChild.data._helper)
        self.assertIs(JIChild._meta.database, db)

        JIChild.create_table()
        try:
            JIChild.create(data={'a': 1}, extra=[1, 2])
            row = JIChild.select().first()
            self.assertEqual(row.data, {'a': 1})
            self.assertEqual(row.extra, [1, 2])
        finally:
            JIChild.drop_table()

    def test_database_not_deepcopied(self):
        from copy import deepcopy
        self.assertIs(deepcopy(db), db)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestNullSemantics(ModelTestCase):
    requires = [JM]

    JSON_NULL_OK = not IS_MYSQL

    def setUp(self):
        super(TestNullSemantics, self).setUp()

        self.r_present = JM.create(data={'k': 'v', 'mark': 1}).id
        if self.JSON_NULL_OK:
            self.r_json_null = JM.create(data={'k': None, 'mark': 2}).id
        self.r_missing = JM.create(data={'mark': 3}).id
        self.r_sql_null = JM.create(data=None).id

        self._null_count = 3 if self.JSON_NULL_OK else 2
        self._present_count = 1

    # Path-level: all null-ish cases match.
    def test_path_eq_none(self):
        n = JM.select().where(JM.data['k'] == None).count()
        self.assertEqual(n, self._null_count)

    def test_path_ne_none(self):
        n = JM.select().where(JM.data['k'] != None).count()
        self.assertEqual(n, self._present_count)

    def test_path_is_null(self):
        n = JM.select().where(JM.data['k'].is_null()).count()
        self.assertEqual(n, self._null_count)

    def test_path_is_null_false(self):
        n = JM.select().where(JM.data['k'].is_null(False)).count()
        self.assertEqual(n, self._present_count)

    # Text-mode: same semantics.
    def test_as_text_eq_none(self):
        n = JM.select().where(JM.data['k'].as_text() == None).count()
        self.assertEqual(n, self._null_count)

    def test_as_text_is_null(self):
        n = JM.select().where(JM.data['k'].as_text().is_null()).count()
        self.assertEqual(n, self._null_count)

    def test_as_text_is_null_false(self):
        n = JM.select().where(JM.data['k'].as_text().is_null(False)).count()
        self.assertEqual(n, self._present_count)

    def test_field_eq_none_only_sql_null(self):
        ids = [r.id for r in JM.select().where(JM.data == None)]
        self.assertEqual(ids, [self.r_sql_null])

    def test_field_is_null_only_sql_null(self):
        ids = [r.id for r in JM.select().where(JM.data.is_null())]
        self.assertEqual(ids, [self.r_sql_null])

    def test_field_is_null_false_excludes_sql_null(self):
        ids = sorted(r.id for r in JM.select().where(JM.data.is_null(False)))
        expected = [self.r_present, self.r_missing]
        if self.JSON_NULL_OK:
            expected.append(self.r_json_null)
        self.assertEqual(ids, sorted(expected))

    # Python value: all null-ish states collapse to None on extract.
    def test_extract_python_value(self):
        # Each row's data['k'] reads back as Python None for every null-ish
        # case, and as 'v' for the present row.
        rows = {r.id: r for r in JM.select(JM.id, JM.data['k'].alias('k'))}
        self.assertEqual(rows[self.r_present].k, 'v')
        self.assertIsNone(rows[self.r_missing].k)
        self.assertIsNone(rows[self.r_sql_null].k)
        if self.JSON_NULL_OK:
            self.assertIsNone(rows[self.r_json_null].k)

    def test_extract_text_python_value(self):
        rows = {r.id: r for r in JM.select(
            JM.id, JM.data['k'].as_text().alias('k'))}
        self.assertEqual(rows[self.r_present].k, 'v')
        self.assertIsNone(rows[self.r_missing].k)
        self.assertIsNone(rows[self.r_sql_null].k)
        if self.JSON_NULL_OK:
            self.assertIsNone(rows[self.r_json_null].k)

    def test_distinguish_missing_vs_json_null_via_fn(self):
        if not self.JSON_NULL_OK:
            self.skipTest('MySQL/MariaDB collapse json null at unquote')
        # Pick the right type function per backend.
        if IS_PG_JSON:
            type_fn = fn.jsonb_typeof(JM.data['k'])
            json_null_marker = 'null'
        elif IS_MYSQL:
            type_fn = fn.json_type(JM.data['k'])
            json_null_marker = 'NULL'
        else:
            type_fn = fn.json_type(JM.data, '$.k')
            json_null_marker = 'null'
        # Rows where the key is present AND is JSON null: only r_json_null.
        ids = [r.id for r in JM.select().where(type_fn == json_null_marker)]
        self.assertEqual(ids, [self.r_json_null])


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestAsTextDeep(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestAsTextDeep, self).setUp()
        JM.create(data={'name': 'apple', 'count': 5,
                        'tags': ['red', 'green']})
        JM.create(data={'name': 'banana', 'count': 50,
                        'tags': ['yellow']})
        JM.create(data={'name': 'cherry', 'count': 100,
                        'tags': ['red', 'dark']})

    def test_eq(self):
        n = JM.select().where(JM.data['name'].as_text() == 'banana').count()
        self.assertEqual(n, 1)

    def test_ne(self):
        n = JM.select().where(JM.data['name'].as_text() != 'banana').count()
        self.assertEqual(n, 2)

    def test_lt(self):
        # Lex compare: apple < b < banana < cherry.
        n = JM.select().where(JM.data['name'].as_text() < 'b').count()
        self.assertEqual(n, 1)

    def test_between(self):
        n = (JM.select()
             .where(JM.data['name'].as_text().between('a', 'c')).count())
        self.assertEqual(n, 2)

    def test_in(self):
        n = (JM.select()
             .where(JM.data['name'].as_text().in_(['apple', 'cherry']))
             .count())
        self.assertEqual(n, 2)

    def test_not_in(self):
        n = (JM.select()
             .where(JM.data['name'].as_text().not_in(['apple']))
             .count())
        self.assertEqual(n, 2)

    def test_text_then_cast(self):
        # MySQL spells the integer cast-type SIGNED (MariaDB accepts both).
        cast_type = 'signed' if IS_MYSQL else 'integer'
        n = (JM.select()
             .where(JM.data['count'].as_text().cast(cast_type) > 10).count())
        self.assertEqual(n, 2)

    def test_ordering(self):
        names = [r.n for r in (JM.select(JM.data['name'].as_text().alias('n'))
                               .order_by(JM.data['name'].as_text()))]
        self.assertEqual(names, ['apple', 'banana', 'cherry'])

    def test_as_text_returns_string_for_number(self):
        # Stored JSON int. Text extract returns the text form on PG/MySQL;
        # SQLite returns the SQL value (loose). Both compare to a numeric
        # equivalent.
        v = JM.select(JM.data['count'].as_text()).where(
            JM.data['name'].as_text() == 'apple').scalar()
        self.assertEqual(int(v), 5)

    def test_as_text_for_container_is_json_text(self):
        v = JM.select(JM.data['tags'].as_text()).where(
            JM.data['name'].as_text() == 'banana').scalar()
        self.assertEqual(json.loads(v), ['yellow'])

    def test_ilike(self):
        n = JM.select().where(JM.data['name'].ilike('a%')).count()
        self.assertEqual(n, 1)

    def test_startswith_endswith_contains(self):
        self.assertEqual(
            JM.select().where(JM.data['name'].startswith('a')).count(), 1)
        self.assertEqual(
            JM.select().where(JM.data['name'].endswith('y')).count(), 1)
        if IS_PG_JSON:
            q = JM.select().where(JM.data['name'].contains('apple'))
            self.assertEqual(q.count(), 1)

    def test_as_text_contains_substring(self):
        # Text-mode contains is a substring LIKE on every backend.
        q = JM.select().where(JM.data['name'].as_text().contains('err'))
        self.assertEqual(q.count(), 1)  # cherry.
        q = JM.select().where(JM.data['name'].as_text().contains('errr'))
        self.assertEqual(q.count(), 0)


class TestSQLShapes(ModelTestCase):
    requires = [JM]

    def _sql(self, query):
        return query.sql()

    def test_schema_per_backend(self):
        ddl, _ = JM._schema._create_table().query()
        if IS_SQLITE:
            self.assertIn('"data" TEXT', ddl)
        elif IS_PG_JSON:
            self.assertIn('"data" JSONB', ddl)
        elif IS_MYSQL:
            self.assertIn('`data` JSON', ddl)

    def test_extract_default_mode(self):
        sql, params = self._sql(JM.select(JM.data['k']))
        if IS_SQLITE:
            self.assertIn(' -> ', sql)
            self.assertIn('$."k"', params)
        elif IS_PG_JSON:
            self.assertIn(' #> ', sql)
            self.assertIn(['k'], params)
        elif IS_MYSQL:
            lower = sql.lower()
            self.assertIn('json_extract', lower)
            if IS_ORACLE_MYSQL:
                # MySQL has no JSON_COMPACT; CAST to its native json type.
                self.assertIn('cast(', lower)
            else:
                # MariaDB byte-compares extracts; JSON_COMPACT normalizes.
                self.assertIn('json_compact', lower)

    def test_extract_text_mode(self):
        sql, _ = self._sql(JM.select(JM.data['k'].as_text()))
        if IS_SQLITE:
            self.assertIn(' ->> ', sql)
        elif IS_PG_JSON:
            self.assertIn(' #>> ', sql)
        elif IS_MYSQL:
            lower = sql.lower()
            self.assertIn('json_unquote', lower)
            self.assertIn('json_extract', lower)


class TestMySQLJSONStaticFlavor(BaseTestCase):
    def _select_sql(self, mariadb, build):
        flavor_db = MySQLDatabase('peewee_test', mariadb=mariadb)

        class M(TestModel):
            data = JSONField()
            class Meta:
                database = flavor_db

        self.assertIsNone(flavor_db.server_version)  # Never connected.
        sql, _ = M.select().where(build(M)).sql()
        return sql

    def test_value_marking_is_static(self):
        path_eq = lambda M: M.data['k'] == 'v'
        mysql_sql = self._select_sql(False, path_eq)
        self.assertIn('CAST(', mysql_sql)
        self.assertNotIn('JSON_COMPACT', mysql_sql)

        maria_sql = self._select_sql(True, path_eq)
        self.assertIn('JSON_COMPACT(', maria_sql)
        self.assertNotIn('CAST(', maria_sql)

    def test_contains_needs_no_marker(self):
        contains = lambda M: M.data.contains({'k': 'v'})
        shapes = set(self._select_sql(m, contains) for m in (False, True))
        self.assertEqual(len(shapes), 1)
        only = shapes.pop()
        self.assertNotIn('JSON_COMPACT', only)
        self.assertNotIn('CAST(', only)


class TestBulkUpdate(ModelTestCase):
    requires = [JM]

    def test_bulk_update_top_level_dict(self):
        a = JM.create(data={'x': 'y1'})
        b = JM.create(data={'x': 'y2'})
        a.data = {'x': 'z1'}
        b.data = {'X': 'Z2'}
        JM.bulk_update([a, b], fields=[JM.data])
        self.assertEqual(JM.get_by_id(a.id).data, {'x': 'z1'})
        self.assertEqual(JM.get_by_id(b.id).data, {'X': 'Z2'})

    def test_bulk_update_top_level_list(self):
        a = JM.create(data=['a', 'b', 'c'])
        b = JM.create(data=['d', 'e', 'f'])
        a.data = ['g', 'h', 'i']
        b.data = ['j', 'k', 'l']
        JM.bulk_update([a, b], fields=[JM.data])
        self.assertEqual(JM.get_by_id(a.id).data, ['g', 'h', 'i'])
        self.assertEqual(JM.get_by_id(b.id).data, ['j', 'k', 'l'])


class TestInsertMany(ModelTestCase):
    requires = [JM]

    def test_insert_many(self):
        JM.insert_many([{'data': {'i': 0}}, {'data': [1, 2]},
                        {'data': None}]).execute()
        vals = [m.data for m in JM.select().order_by(JM.id)]
        self.assertEqual(vals, [{'i': 0}, [1, 2], None])

        JM.delete().execute()
        JM.insert_many([({'j': 1},), ('scalar',)],
                       fields=[JM.data]).execute()
        vals = [m.data for m in JM.select().order_by(JM.id)]
        self.assertEqual(vals, [{'j': 1}, 'scalar'])


class TestSubqueryAssign(ModelTestCase):
    requires = [JM]

    @skip_if(IS_ORACLE_MYSQL, 'MySQL: ER_UPDATE_TABLE_USED')
    def test_assign_via_subquery(self):
        src = JM.create(data={'origin': True, 'n': 7})
        sub = JM.select(JM.data).where(JM.id == src.id)
        dst = JM.create(data=sub)
        self.assertEqual(JM.get_by_id(dst.id).data, {'origin': True, 'n': 7})


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestJoinOnJSONKey(ModelTestCase):
    requires = [JM, TM]

    def setUp(self):
        super(TestJoinOnJSONKey, self).setUp()
        for data in (
                {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
                {'foo': 'bar', 'baze': {'nugget': 'beta'}},
                {'herp': 'derp', 'baze': {'nugget': 'epsilon'}},
                {'herp': 'derp', 'bar': {'nuggie': 'alpha'}}):
            JM.create(data=data)
        for v in ('alpha', 'beta', 'gamma', 'delta'):
            TM.create(text=v)

    def test_join_path_as_text(self):
        q = (JM.select()
             .join(TM, on=(TM.text == JM.data['baze']['nugget'].as_text()))
             .order_by(JM.id))
        results = [m.data for m in q]
        self.assertEqual(results, [
            {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
            {'foo': 'bar', 'baze': {'nugget': 'beta'}},
        ])


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestMutation(ModelTestCase):
    requires = [JM]

    def test_set_scalar(self):
        m = JM.create(data={'k': 'v', 'n': 5})
        JM.update(data=JM.data['k'].set('updated')).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'k': 'updated', 'n': 5})

    def test_set_container(self):
        m = JM.create(data={'k': 'v'})
        JM.update(data=JM.data['k'].set({'a': 1, 'b': [2]})).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'k': {'a': 1, 'b': [2]}})

    def test_set_json_null(self):
        # set(None) stores JSON null at the path, NOT SQL NULL on the column,
        # and on MySQL must not trigger the "any-arg-NULL wipes document"
        # footgun.
        m = JM.create(data={'k': 'v'})
        JM.update(data=JM.data['k'].set(None)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'k': None})

    def test_remove(self):
        m = JM.create(data={'k': 'v', 'n': 5})
        JM.update(data=JM.data['k'].remove()).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'n': 5})

    def test_length_array(self):
        JM.create(data={'tags': ['a', 'b', 'c']})
        JM.create(data={'tags': []})
        rows = list(JM.select(JM.data['tags'].length().alias('L')).order_by(JM.id))
        self.assertEqual([r.L for r in rows], [3, 0])

    def test_length_root(self):
        # length() on root: array length of the document IF it's an array.
        JM.create(data=['a', 'b', 'c'])
        L = JM.select(JM.data.length()).scalar()
        self.assertEqual(L, 3)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestInsertReplaceAppend(ModelTestCase):
    requires = [JM]

    def test_insert_missing(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['new'].insert(99)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': 1, 'new': 99})

    def test_insert_existing_is_noop(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['a'].insert(99)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': 1})

    def test_insert_existing_json_null_is_noop(self):
        # A stored JSON null counts as "present" for insert, slot is
        # occupied, so insert() leaves it alone on every backend. The
        # Postgres CASE wrapper relies on `field -> 'k'` returning jsonb
        # 'null' (not SQL NULL) for stored JSON nulls so IS NULL is FALSE.
        m = JM.create(data={'a': None})
        JM.update(data=JM.data['a'].insert(99)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': None})

    def test_insert_container(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['new'].insert({'b': 2})).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': 1, 'new': {'b': 2}})

    def test_replace_existing(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['a'].replace(99)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': 99})

    def test_replace_missing_is_noop(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['new'].replace(99)).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': 1})

    def test_replace_container(self):
        m = JM.create(data={'a': 1})
        JM.update(data=JM.data['a'].replace({'b': 2})).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'a': {'b': 2}})

    def test_append_path(self):
        m = JM.create(data={'tags': ['a', 'b']})
        JM.update(data=JM.data['tags'].append('c')).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'tags': ['a', 'b', 'c']})

    def test_append_container(self):
        m = JM.create(data={'items': [1]})
        JM.update(data=JM.data['items'].append({'k': 'v'})).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, {'items': [1, {'k': 'v'}]})

    def test_append_root(self):
        m = JM.create(data=['a', 'b'])
        JM.update(data=JM.data.append('c')).where(JM.id == m.id).execute()
        self.assertEqual(JM.get_by_id(m.id).data, ['a', 'b', 'c'])


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestUpdateDivergence(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestUpdateDivergence, self).setUp()
        JM.create(data={'k': 'v', 'nested': {'a': 1, 'b': 2}})

    def test_update_adds_top_level_key(self):
        # Adding a new top-level key works the same on all backends.
        JM.update(data=JM.data.update({'new': 1})).execute()
        m = JM.select().get()
        self.assertEqual(m.data['new'], 1)
        self.assertEqual(m.data['k'], 'v')

    def test_update_nested_keys_diverge(self):
        # On SQLite/MySQL/MariaDB: deep merge preserves the un-overwritten
        # nested key 'a'. On PostgreSQL: shallow concat overwrites the entire
        # 'nested' value, dropping 'a'.
        JM.update(data=JM.data.update({'nested': {'b': 99}})).execute()
        m = JM.select().get()
        if IS_PG_JSON:
            self.assertEqual(m.data['nested'], {'b': 99})  # 'a' dropped
        else:
            self.assertEqual(m.data['nested'], {'a': 1, 'b': 99})

    def test_update_null_deletes_diverge(self):
        # On SQLite/MySQL/MariaDB (RFC-7396): null deletes the key.
        # On PostgreSQL: null is stored as JSON null at the top level.
        JM.update(data=JM.data.update({'k': None})).execute()
        m = JM.select().get()
        if IS_PG_JSON:
            self.assertIn('k', m.data)
            self.assertIsNone(m.data['k'])
        else:
            self.assertNotIn('k', m.data)


@skip_if(SKIP_PATHS, 'requires SQLite 3.38 or non-SQLite backend')
class TestDocumentedDivergences(ModelTestCase):
    # Pin the per-backend behaviors promised in the docs, so the docs and
    # the implementation cannot drift apart silently.
    requires = [JM]

    def test_set_missing_parents(self):
        JM.create(data={})
        JM.update(data=JM.data['a']['b'].set(1)).execute()
        data = JM.select().get().data
        if IS_SQLITE:
            self.assertEqual(data, {'a': {'b': 1}})  # Chain is created.
        else:
            self.assertEqual(data, {})  # Silent no-op on PG and MySQL.

    def test_append_non_array_object(self):
        JM.create(data={'a': {'b': 1}})
        JM.update(data=JM.data['a'].append('x')).execute()
        data = JM.select().get().data
        if IS_SQLITE:
            self.assertEqual(data, {'a': {'b': 1}})  # Silent no-op.
        elif IS_MYSQL:
            self.assertEqual(data, {'a': [{'b': 1}, 'x']})  # Wrapped.
        else:
            self.assertEqual(data, {'a': {'b': 1, '-1': 'x'}})  # PG -1 key.

    def test_append_non_array_scalar(self):
        JM.create(data={'a': 1})
        JM.update(data=JM.data['a'].append('x')).execute()
        data = JM.select().get().data
        if IS_MYSQL:
            self.assertEqual(data, {'a': [1, 'x']})  # Wrapped.
        else:
            self.assertEqual(data, {'a': 1})  # No-op on SQLite and PG.

    def test_append_missing_path(self):
        JM.create(data={})
        JM.update(data=JM.data['tags'].append('x')).execute()
        data = JM.select().get().data
        if IS_SQLITE:
            self.assertEqual(data, {'tags': ['x']})  # Array is created.
        elif IS_MARIADB:
            # JSON_ARRAY_APPEND returns SQL NULL for a missing path, which
            # nulls the whole column. Documented footgun.
            self.assertIsNone(data)
        else:
            self.assertEqual(data, {})  # Ignored on PG and MySQL.

    def test_length_non_array(self):
        JM.create(data={'k': {'a': 1, 'b': 2}})
        query = JM.select(JM.data['k'].length())
        if IS_PG_JSON:
            with self.assertRaises((DataError, ProgrammingError)):
                with self.database.atomic():
                    query.scalar()
        elif IS_MYSQL:
            self.assertEqual(query.scalar(), 2)  # Object key count.
        else:
            self.assertEqual(query.scalar(), 0)  # SQLite: 0 for non-array.

    @skip_if(IS_CRDB)
    def test_default_mode_ordering(self):
        JM.create(data={'n': 10})
        JM.create(data={'n': 2})
        # Numerically only n=10 exceeds 5; under text comparison neither
        # '10' nor '2' exceeds '5'.
        n = JM.select().where(JM.data['n'] > 5).count()
        if IS_PG_JSON or IS_ORACLE_MYSQL:
            self.assertEqual(n, 1)  # Typed (numeric) comparison.
        else:
            self.assertEqual(n, 0)  # SQLite/MariaDB: lexicographic text.

        # as_int() is numeric everywhere.
        n = JM.select().where(JM.data['n'].as_int() > 5).count()
        self.assertEqual(n, 1)


# JSON structural containment (@> / <@). Native on PG and MySQL/MariaDB;
# emulated on SQLite via the _pw_json_contains() UDF.
class TestContainment(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestContainment, self).setUp()
        JM.create(data={'k': 'v', 'tags': ['python', 'orm'],
                        'meta': {'env': 'prod', 'region': 'us'}})
        JM.create(data={'k': 'v', 'tags': ['rust']})
        JM.create(data={'k': 'other'})

    def test_contains_root(self):
        # Subset match at the root level.
        q = JM.select().where(JM.data.contains({'k': 'v'}))
        self.assertEqual(q.count(), 2)

    def test_contains_nested(self):
        q = JM.select().where(JM.data.contains({'meta': {'env': 'prod'}}))
        self.assertEqual(q.count(), 1)

    def test_contains_path(self):
        # Sub-extract containment: data['tags'] @> ['python']
        q = JM.select().where(JM.data['tags'].contains(['python']))
        self.assertEqual(q.count(), 1)

    def test_contained_by(self):
        bigger = {'k': 'v', 'tags': ['python', 'orm', 'sql'],
                  'meta': {'env': 'prod', 'region': 'us'}, 'extra': True}
        q = JM.select().where(JM.data.contained_by(bigger))
        # Row 1 fits inside `bigger`; rows 2 and 3 don't.
        self.assertEqual(q.count(), 1)

    def test_contained_by_on_path(self):
        q = JM.select().where(
            JM.data['tags'].contained_by(['python', 'orm', 'sql']))
        self.assertEqual(q.count(), 1)

    def test_contains_scalar_in_array(self):
        # Array containment matches a bare scalar element (PG/MySQL parity).
        q = JM.select().where(JM.data['tags'].contains('python'))
        self.assertEqual(q.count(), 1)

    def test_contains_bool_not_int(self):
        # JSON true/false must not be matched by 1/0, or vice versa.
        JM.create(data={'flag': True, 'n': 1})
        self.assertEqual(
            JM.select().where(JM.data.contains({'flag': True})).count(), 1)
        self.assertEqual(
            JM.select().where(JM.data.contains({'flag': 1})).count(), 0)
        self.assertEqual(
            JM.select().where(JM.data.contains({'n': True})).count(), 0)

    @skip_if(IS_MYSQL, 'MySQL/MariaDB use looser recursive containment')
    def test_contains_level_aligned(self):
        # PG and SQLite match containment level-by-level: a scalar in the
        # needle only matches a top-level array element, so a value buried in
        # a nested array does not count (recursive descent would flip these).
        JM.create(data={'nested': [1, 2, [1, 3]]})
        self.assertEqual(
            JM.select().where(JM.data['nested'].contains([3])).count(), 0)
        self.assertEqual(
            JM.select().where(JM.data['nested'].contains([[1, 3]])).count(), 1)


# Key-existence predicates are portable to every backend: PG (?/?&/?|),
# MySQL/MariaDB (JSON_CONTAINS_PATH), and SQLite (json_type() IS NOT NULL).
class TestKeyExistence(ModelTestCase):
    requires = [JM]

    def setUp(self):
        super(TestKeyExistence, self).setUp()
        JM.create(data={'k': 'v', 'tags': ['python', 'orm'],
                        'meta': {'env': 'prod', 'region': 'us'}})
        JM.create(data={'k': 'v', 'tags': ['rust']})
        JM.create(data={'k': 'other'})

    def test_has_key(self):
        q = JM.select().where(JM.data.has_key('meta'))
        self.assertEqual(q.count(), 1)

    def test_has_keys(self):
        q = JM.select().where(JM.data.has_keys(['k', 'tags']))
        self.assertEqual(q.count(), 2)

    def test_has_any_keys(self):
        q = JM.select().where(JM.data.has_any_keys(['nope', 'meta']))
        self.assertEqual(q.count(), 1)

    def test_has_key_on_path(self):
        q = JM.select().where(JM.data['meta'].has_key('env'))
        self.assertEqual(q.count(), 1)

    def test_has_keys_on_path(self):
        q = JM.select().where(JM.data['meta'].has_keys(['env', 'region']))
        self.assertEqual(q.count(), 1)
        q = JM.select().where(JM.data['meta'].has_keys(['env', 'nope']))
        self.assertEqual(q.count(), 0)

    def test_has_any_keys_on_path(self):
        q = JM.select().where(JM.data['meta'].has_any_keys(['nope', 'env']))
        self.assertEqual(q.count(), 1)
