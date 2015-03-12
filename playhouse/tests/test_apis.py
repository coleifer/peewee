from peewee import Node
from peewee import *
from playhouse.tests.base import PeeweeTestCase


class TestNodeAPI(PeeweeTestCase):
    def test_extend(self):
        @Node.extend()
        def add(self, lhs, rhs):
            return lhs + rhs

        n = Node()
        self.assertEqual(n.add(4, 2), 6)
        delattr(Node, 'add')
        self.assertRaises(AttributeError, lambda: n.add(2, 4))

    def test_clone(self):
        @Node.extend(clone=True)
        def hack(self, alias):
            self._negated = True
            self._alias = alias

        n = Node()
        c = n.hack('magic!')
        self.assertFalse(n._negated)
        self.assertEqual(n._alias, None)
        self.assertTrue(c._negated)
        self.assertEqual(c._alias, 'magic!')

        class TestModel(Model):
            data = CharField()

        hacked = TestModel.data.hack('nugget')
        self.assertFalse(TestModel.data._negated)
        self.assertEqual(TestModel.data._alias, None)
        self.assertTrue(hacked._negated)
        self.assertEqual(hacked._alias, 'nugget')

        delattr(Node, 'hack')
        self.assertRaises(AttributeError, lambda: TestModel.data.hack())
