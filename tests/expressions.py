from peewee import *

from .base import skip_if
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel


class Person(TestModel):
    name = CharField()


class BaseNamesTest(ModelTestCase):
    requires = [Person]

    def assertNames(self, exp, x):
        query = Person.select().where(exp).order_by(Person.name)
        self.assertEqual([p.name for p in query], x)



class TestRegexp(BaseNamesTest):
    @skip_if(IS_SQLITE)
    def test_regexp_iregexp(self):
        people = [Person.create(name=name) for name in ('n1', 'n2', 'n3')]

        self.assertNames(Person.name.regexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(Person.name.regexp('N[1,3]'), [])
        self.assertNames(Person.name.iregexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(Person.name.iregexp('N[1,3]'), ['n1', 'n3'])


class TestContains(BaseNamesTest):
    def test_contains_startswith_endswith(self):
        people = [Person.create(name=n) for n in ('huey', 'mickey', 'zaizee')]

        self.assertNames(Person.name.contains('ey'), ['huey', 'mickey'])
        self.assertNames(Person.name.contains('EY'), ['huey', 'mickey'])

        self.assertNames(Person.name.startswith('m'), ['mickey'])
        self.assertNames(Person.name.startswith('M'), ['mickey'])

        self.assertNames(Person.name.endswith('ey'), ['huey', 'mickey'])
        self.assertNames(Person.name.endswith('EY'), ['huey', 'mickey'])
