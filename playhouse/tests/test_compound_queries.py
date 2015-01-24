import itertools
import operator
from functools import wraps

from playhouse.tests.base import compiler
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import test_db
from playhouse.tests.models import *


class TestCompoundSelectQueries(ModelTestCase):
    requires = [User, UniqueModel, OrderedModel]
    # User -> username, UniqueModel -> name, OrderedModel -> title
    test_values = {
        User.username: ['a', 'b', 'c', 'd'],
        UniqueModel.name: ['b', 'd', 'e'],
        OrderedModel.title: ['a', 'c', 'e'],
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
                elif TEST_VERBOSITY > 0:
                    print_('"%s" not supported, skipping %s' %
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
        uq = User.select(User.username).where(User.username << ['a', 'b', 'd'])
        oq = (OrderedModel
              .select(OrderedModel.title)
              .where(OrderedModel.title << ['a', 'b'])
              .order_by())
        iq = UniqueModel.select(UniqueModel.name)
        union = uq | oq | iq

        query = User.select(SQL('1')).from_(union)
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT 1 FROM ('
            'SELECT "users"."username" FROM "users" AS users '
            'WHERE ("users"."username" IN (?, ?, ?)) '
            'UNION '
            'SELECT "orderedmodel"."title" FROM "orderedmodel" AS orderedmodel'
            ' WHERE ("orderedmodel"."title" IN (?, ?)) '
            'UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel'
            ')'))
        self.assertEqual(params, ['a', 'b', 'd', 'a', 'b'])

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
    def test_union_sql(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        sql, params = compiler.generate_select(union)
        self.assertEqual(sql, (
            'SELECT "users"."username" FROM "users" AS users UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel'))

    @requires_op('UNION')
    def test_union_subquery(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        query = User.select().where(User.username << union)
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username" '
            'FROM "users" AS users WHERE ("users"."username" IN '
            '(SELECT "users"."username" FROM "users" AS users UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel))'))

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
