import itertools
import operator
import sys
if sys.version_info[0] != 3:
    from functools import reduce
from functools import wraps

from peewee import *
from playhouse.tests.base import compiler
from playhouse.tests.base import database_initializer
from playhouse.tests.base import log_console
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_test_if
from playhouse.tests.base import skip_unless
from playhouse.tests.base import test_db
from playhouse.tests.models import *

compound_db = database_initializer.get_in_memory_database()

class CompoundBase(Model):
    class Meta:
        database = compound_db

class Alpha(CompoundBase):
    alpha = IntegerField()

class Beta(CompoundBase):
    beta = IntegerField()
    other = IntegerField(default=0)

class Gamma(CompoundBase):
    gamma = IntegerField()
    other = IntegerField(default=1)


class TestCompoundSelectSQL(PeeweeTestCase):
    def setUp(self):
        super(TestCompoundSelectSQL, self).setUp()
        compound_db.compound_select_parentheses = False  # Restore default.
        self.a1 = Alpha.select(Alpha.alpha).where(Alpha.alpha < 2)
        self.a2 = Alpha.select(Alpha.alpha).where(Alpha.alpha > 5)
        self.b1 = Beta.select(Beta.beta).where(Beta.beta < 3)
        self.b2 = Beta.select(Beta.beta).where(Beta.beta > 4)

    def test_simple_sql(self):
        lhs = Alpha.select(Alpha.alpha)
        rhs = Beta.select(Beta.beta)
        sql, params = (lhs | rhs).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2'))

        sql, params = (
            Alpha.select(Alpha.alpha) |
            Beta.select(Beta.beta) |
            Gamma.select(Gamma.gamma)).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2 UNION '
            'SELECT "t3"."gamma" FROM "gamma" AS t3'))

        sql, params = (
            Alpha.select(Alpha.alpha) |
            (Beta.select(Beta.beta) |
             Gamma.select(Gamma.gamma))).sql()
        self.assertEqual(sql, (
            'SELECT "t3"."alpha" FROM "alpha" AS t3 UNION '
            'SELECT "t1"."beta" FROM "beta" AS t1 UNION '
            'SELECT "t2"."gamma" FROM "gamma" AS t2'))

    def test_simple_same_model(self):
        queries = [Alpha.select(Alpha.alpha) for i in range(3)]
        lhs = queries[0] | queries[1]
        compound = lhs | queries[2]
        sql, params = compound.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS t2 UNION '
            'SELECT "t3"."alpha" FROM "alpha" AS t3'))

        lhs = queries[0]
        compound = lhs | (queries[1] | queries[2])
        sql, params = compound.sql()
        self.assertEqual(sql, (
            'SELECT "t3"."alpha" FROM "alpha" AS t3 UNION '
            'SELECT "t1"."alpha" FROM "alpha" AS t1 UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS t2'))

    def test_where_clauses(self):
        sql, params = (self.a1 | self.a2).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS t2 WHERE ("t2"."alpha" > ?)'))
        self.assertEqual(params, [2, 5])

        sql, params = (self.a1 | self.b1).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2 WHERE ("t2"."beta" < ?)'))
        self.assertEqual(params, [2, 3])

        sql, params = (self.a1 | self.b1 | self.a2 | self.b2).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2 WHERE ("t2"."beta" < ?) '
            'UNION '
            'SELECT "t4"."alpha" FROM "alpha" AS t4 WHERE ("t4"."alpha" > ?) '
            'UNION '
            'SELECT "t3"."beta" FROM "beta" AS t3 WHERE ("t3"."beta" > ?)'))
        self.assertEqual(params, [2, 3, 5, 4])

    def test_outer_limit(self):
        sql, params = (self.a1 | self.a2).limit(3).sql()
        self.assertEqual(sql, (
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS t2 WHERE ("t2"."alpha" > ?) '
            'LIMIT 3'))

    def test_union_in_from(self):
        compound = (self.a1 | self.a2).alias('cq')
        sql, params = Alpha.select(compound.c.alpha).from_(compound).sql()
        self.assertEqual(sql, (
            'SELECT "cq"."alpha" FROM ('
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS t2 WHERE ("t2"."alpha" > ?)'
            ') AS cq'))

        compound = (self.a1 | self.b1 | self.b2).alias('cq')
        sql, params = Alpha.select(SQL('1')).from_(compound).sql()
        self.assertEqual(sql, (
            'SELECT 1 FROM ('
            'SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2 WHERE ("t2"."beta" < ?) '
            'UNION '
            'SELECT "t3"."beta" FROM "beta" AS t3 WHERE ("t3"."beta" > ?)'
            ') AS cq'))
        self.assertEqual(params, [2, 3, 4])

    def test_parentheses(self):
        compound_db.compound_select_parentheses = True

        sql, params = (self.a1 | self.a2).sql()
        self.assertEqual(sql, (
            '(SELECT "t1"."alpha" FROM "alpha" AS t1 '
            'WHERE ("t1"."alpha" < ?)) '
            'UNION '
            '(SELECT "t2"."alpha" FROM "alpha" AS t2 '
            'WHERE ("t2"."alpha" > ?))'))
        self.assertEqual(params, [2, 5])

    def test_multiple_with_parentheses(self):
        compound_db.compound_select_parentheses = True

        queries = [Alpha.select(Alpha.alpha) for i in range(3)]
        lhs = queries[0] | queries[1]
        compound = lhs | queries[2]
        sql, params = compound.sql()
        self.assertEqual(sql, (
            '((SELECT "t1"."alpha" FROM "alpha" AS t1) UNION '
            '(SELECT "t2"."alpha" FROM "alpha" AS t2)) UNION '
            '(SELECT "t3"."alpha" FROM "alpha" AS t3)'))

        lhs = queries[0]
        compound = lhs | (queries[1] | queries[2])
        sql, params = compound.sql()
        self.assertEqual(sql, (
            '(SELECT "t3"."alpha" FROM "alpha" AS t3) UNION '
            '((SELECT "t1"."alpha" FROM "alpha" AS t1) UNION '
            '(SELECT "t2"."alpha" FROM "alpha" AS t2))'))

    def test_inner_limit(self):
        compound_db.compound_select_parentheses = True
        a1 = Alpha.select(Alpha.alpha).where(Alpha.alpha < 2).limit(2)
        a2 = Alpha.select(Alpha.alpha).where(Alpha.alpha > 5).limit(4)
        sql, params = (a1 | a2).limit(3).sql()

        self.assertEqual(sql, (
            '(SELECT "t1"."alpha" FROM "alpha" AS t1 WHERE ("t1"."alpha" < ?) '
            'LIMIT 2) '
            'UNION '
            '(SELECT "t2"."alpha" FROM "alpha" AS t2 WHERE ("t2"."alpha" > ?) '
            'LIMIT 4) '
            'LIMIT 3'))

    def test_union_subquery(self):
        union = (Alpha.select(Alpha.alpha) |
                 Beta.select(Beta.beta))
        query = Alpha.select().where(Alpha.alpha << union)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."alpha" '
            'FROM "alpha" AS t1 WHERE ("t1"."alpha" IN ('
            'SELECT "t1"."alpha" FROM "alpha" AS t1 '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS t2))'))


class TestCompoundSelectQueries(ModelTestCase):
    requires = [User, UniqueModel, OrderedModel, Blog]
    # User -> username, UniqueModel -> name, OrderedModel -> title
    test_values = {
        User.username: ['a', 'b', 'c', 'd'],
        OrderedModel.title: ['a', 'c', 'e'],
        UniqueModel.name: ['b', 'd', 'e'],
    }

    def setUp(self):
        super(TestCompoundSelectQueries, self).setUp()
        for field, values in self.test_values.items():
            for value in values:
                field.model_class.create(**{field.name: value})

    def requires_op(op):
        def decorator(fn):
            @wraps(fn)
            def inner(self):
                if op in test_db.compound_operations:
                    return fn(self)
                else:
                    log_console('"%s" not supported, skipping %s' %
                                (op, fn.__name__))
            return inner
        return decorator

    def assertValues(self, query, expected):
        self.assertEqual(sorted(query.tuples()),
                         [(x,) for x in sorted(expected)])

    def assertPermutations(self, op, expected):
        fields = {
            User: User.username,
            UniqueModel: UniqueModel.name,
            OrderedModel: OrderedModel.title,
        }
        for key in itertools.permutations(fields.keys(), 2):
            if key in expected:
                left, right = key
                query = op(left.select(fields[left]).order_by(),
                           right.select(fields[right]).order_by())
                # Ensure the sorted tuples returned from the query are equal
                # to the sorted values we expected for this combination.
                self.assertValues(query, expected[key])

    @requires_op('UNION')
    def test_union(self):
        all_letters = ['a', 'b', 'c', 'd', 'e']
        self.assertPermutations(operator.or_, {
            (User, UniqueModel): all_letters,
            (User, OrderedModel): all_letters,
            (UniqueModel, User): all_letters,
            (UniqueModel, OrderedModel): all_letters,
            (OrderedModel, User): all_letters,
            (OrderedModel, UniqueModel): all_letters,
        })

    @requires_op('UNION ALL')
    def test_union(self):
        all_letters = ['a', 'b', 'c', 'd', 'e']
        users = User.select(User.username)
        uniques = UniqueModel.select(UniqueModel.name)
        query = users.union_all(uniques)
        results = [row[0] for row in query.tuples()]
        self.assertEqual(sorted(results), ['a', 'b', 'b', 'c', 'd', 'd', 'e'])

    @requires_op('UNION')
    def test_union_from(self):
        uq = (User
              .select(User.username.alias('name'))
              .where(User.username << ['a', 'b', 'd']))

        oq = (OrderedModel
              .select(OrderedModel.title.alias('name'))
              .where(OrderedModel.title << ['a', 'b'])
              .order_by())

        iq = (UniqueModel
              .select(UniqueModel.name.alias('name'))
              .where(UniqueModel.name << ['c', 'd']))

        union_q = (uq | oq | iq).alias('union_q')

        query = (User
                 .select(union_q.c.name)
                 .from_(union_q)
                 .order_by(union_q.c.name.desc()))
        self.assertEqual([row[0] for row in query.tuples()], ['d', 'b', 'a'])

    @requires_op('UNION')
    def test_union_count(self):
        a = User.select().where(User.username == 'a')
        c_and_d = User.select().where(User.username << ['c', 'd'])
        self.assertEqual(a.count(), 1)
        self.assertEqual(c_and_d.count(), 2)

        union = a | c_and_d
        self.assertEqual(union.wrapped_count(), 3)

        overlapping = User.select() | c_and_d
        self.assertEqual(overlapping.wrapped_count(), 4)

    @requires_op('INTERSECT')
    def test_intersect(self):
        self.assertPermutations(operator.and_, {
            (User, UniqueModel): ['b', 'd'],
            (User, OrderedModel): ['a', 'c'],
            (UniqueModel, User): ['b', 'd'],
            (UniqueModel, OrderedModel): ['e'],
            (OrderedModel, User): ['a', 'c'],
            (OrderedModel, UniqueModel): ['e'],
        })

    @requires_op('EXCEPT')
    def test_except(self):
        self.assertPermutations(operator.sub, {
            (User, UniqueModel): ['a', 'c'],
            (User, OrderedModel): ['b', 'd'],
            (UniqueModel, User): ['e'],
            (UniqueModel, OrderedModel): ['b', 'd'],
            (OrderedModel, User): ['e'],
            (OrderedModel, UniqueModel): ['a', 'c'],
        })

    @requires_op('INTERSECT')
    @requires_op('EXCEPT')
    def test_symmetric_difference(self):
        self.assertPermutations(operator.xor, {
            (User, UniqueModel): ['a', 'c', 'e'],
            (User, OrderedModel): ['b', 'd', 'e'],
            (UniqueModel, User): ['a', 'c', 'e'],
            (UniqueModel, OrderedModel): ['a', 'b', 'c', 'd'],
            (OrderedModel, User): ['b', 'd', 'e'],
            (OrderedModel, UniqueModel): ['a', 'b', 'c', 'd'],
        })

    def test_model_instances(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        query = union.order_by(SQL('username').desc()).limit(3)
        self.assertEqual([user.username for user in query],
                         ['e', 'd', 'c'])

    @requires_op('UNION')
    @requires_op('INTERSECT')
    def test_complex(self):
        left = User.select(User.username).where(User.username << ['a', 'b'])
        right = UniqueModel.select(UniqueModel.name).where(
            UniqueModel.name << ['b', 'd', 'e'])

        query = (left & right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [{'username': 'b'}])

        query = (left | right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [
            {'username': 'a'},
            {'username': 'b'},
            {'username': 'd'},
            {'username': 'e'}])

    @requires_op('UNION')
    @skip_test_if(lambda: isinstance(test_db, MySQLDatabase))  # MySQL needs parens, but doesn't like them here.
    def test_union_subquery(self):
        union = (User.select(User.username).where(User.username == 'a') |
                 UniqueModel.select(UniqueModel.name))
        query = (User
                 .select(User.username)
                 .where(User.username << union)
                 .order_by(User.username.desc()))
        self.assertEqual(list(query.dicts()), [
            {'username': 'd'},
            {'username': 'b'},
            {'username': 'a'}])

    @requires_op('UNION')
    def test_result_wrapper(self):
        users = User.select().order_by(User.username)
        for user in users:
            for msg in ['foo', 'bar', 'baz']:
                Blog.create(title='%s-%s' % (user.username, msg), user=user)

        with self.assertQueryCount(1):
            q1 = (Blog
                  .select(Blog, User)
                  .join(User)
                  .where(Blog.title.contains('foo')))
            q2 = (Blog
                  .select(Blog, User)
                  .join(User)
                  .where(Blog.title.contains('baz')))
            cq = (q1 | q2).order_by(SQL('username, title'))
            results = [(b.user.username, b.title) for b in cq]

        self.assertEqual(results, [
            ('a', 'a-baz'),
            ('a', 'a-foo'),
            ('b', 'b-baz'),
            ('b', 'b-foo'),
            ('c', 'c-baz'),
            ('c', 'c-foo'),
            ('d', 'd-baz'),
            ('d', 'd-foo'),
        ])

    @requires_op('UNION')
    def test_union_with_count(self):
        lhs = User.select().where(User.username << ['a', 'b'])
        rhs = User.select().where(User.username << ['d', 'x'])
        cq = (lhs | rhs)
        self.assertEqual(cq.count(), 3)


@skip_unless(lambda: isinstance(test_db, PostgresqlDatabase))
class TestCompoundWithOrderLimit(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestCompoundWithOrderLimit, self).setUp()
        for username in ['a', 'b', 'c', 'd', 'e', 'f']:
            User.create(username=username)

    def test_union_with_order_limit(self):
        lhs = (User
               .select(User.username)
               .where(User.username << ['a', 'b', 'c']))
        rhs = (User
               .select(User.username)
               .where(User.username << ['d', 'e', 'f']))

        cq = (lhs.order_by(User.username.desc()).limit(2) |
              rhs.order_by(User.username.desc()).limit(2))
        results = [user.username for user in cq]
        self.assertEqual(sorted(results), ['b', 'c', 'e', 'f'])

        cq = cq.order_by(cq.c.username.desc()).limit(3)
        results = [user.username for user in cq]
        self.assertEqual(results, ['f', 'e', 'c'])
