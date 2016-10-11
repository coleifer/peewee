from peewee import *
from peewee import sort_models_topologically
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import test_db


class TestHelperMethods(PeeweeTestCase):
    def test_assert_query_count(self):
        def execute_queries(n):
            for i in range(n):
                test_db.execute_sql('select 1;')

        with self.assertQueryCount(0):
            pass

        with self.assertQueryCount(1):
            execute_queries(1)

        with self.assertQueryCount(2):
            execute_queries(2)

        def fails_low():
            with self.assertQueryCount(2):
                execute_queries(1)

        def fails_high():
            with self.assertQueryCount(1):
                execute_queries(2)

        self.assertRaises(AssertionError, fails_low)
        self.assertRaises(AssertionError, fails_high)


class TestTopologicalSorting(PeeweeTestCase):
    def test_topological_sort_fundamentals(self):
        FKF = ForeignKeyField
        # we will be topo-sorting the following models
        class A(Model): pass
        class B(Model): a = FKF(A)              # must follow A
        class C(Model): a, b = FKF(A), FKF(B)   # must follow A and B
        class D(Model): c = FKF(C)              # must follow A and B and C
        class E(Model): e = FKF('self')
        # but excluding this model, which is a child of E
        class Excluded(Model): e = FKF(E)

        # property 1: output ordering must not depend upon input order
        repeatable_ordering = None
        for input_ordering in permutations([A, B, C, D, E]):
            output_ordering = sort_models_topologically(input_ordering)
            repeatable_ordering = repeatable_ordering or output_ordering
            self.assertEqual(repeatable_ordering, output_ordering)

        # property 2: output ordering must have same models as input
        self.assertEqual(len(output_ordering), 5)
        self.assertFalse(Excluded in output_ordering)

        # property 3: parents must precede children
        def assert_precedes(X, Y):
            lhs, rhs = map(output_ordering.index, [X, Y])
            self.assertTrue(lhs < rhs)
        assert_precedes(A, B)
        assert_precedes(B, C)  # if true, C follows A by transitivity
        assert_precedes(C, D)  # if true, D follows A and B by transitivity

        # property 4: independent model hierarchies must be in name order
        assert_precedes(A, E)


class TestDeclaredDependencies(PeeweeTestCase):
    def test_declared_dependencies(self):
        class A(Model): pass
        class B(Model):
            a = ForeignKeyField(A)
            b = ForeignKeyField('self')
        class NA(Model):
            class Meta:
                depends_on = (A, B)
        class C(Model):
            b = ForeignKeyField(B)
            c = ForeignKeyField('self')
            class Meta:
                depends_on = (NA,)
        class D1(Model):
            na = ForeignKeyField(NA)
            class Meta:
                depends_on = (A, C)
        class D2(Model):
            class Meta:
                depends_on = (NA, D1, C, B)

        models = [A, B, C, D1, D2]
        ordered = list(models)
        for pmodels in permutations(models):
            ordering = sort_models_topologically(pmodels)
            self.assertEqual(ordering, ordered)


def permutations(xs):
    if not xs:
        yield []
    else:
        for y, ys in selections(xs):
            for pys in permutations(ys):
                yield [y] + pys

def selections(xs):
    for i in range(len(xs)):
        yield (xs[i], xs[:i] + xs[i + 1:])
