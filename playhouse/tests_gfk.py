import unittest

from peewee import *
from playhouse.gfk import *


db = SqliteDatabase(':memory:')

class BaseModel(Model):
    class Meta:
        database = db

    def add_tag(self, tag):
        t = Tag(tag=tag)
        t.object = self
        t.save()
        return t

class Tag(BaseModel):
    tag = CharField()

    object_type = CharField(null=True)
    object_id = IntegerField(null=True)
    object = GFKField()

    class Meta:
        order_by = ('tag',)


class Appetizer(BaseModel):
    name = CharField()
    tags = ReverseGFK(Tag)

class Entree(BaseModel):
    name = CharField()
    tags = ReverseGFK(Tag)

class Dessert(BaseModel):
    name = CharField()
    tags = ReverseGFK(Tag)



class GFKTestCase(unittest.TestCase):
    data = {
        Appetizer: (
            ('wings', ('fried', 'spicy')),
            ('mozzarella sticks', ('fried', 'sweet')),
            ('potstickers', ('fried',)),
            ('edamame', ('salty',)),
        ),
        Entree: (
            ('phad thai', ('spicy',)),
            ('fried chicken', ('fried', 'salty')),
            ('tacos', ('fried', 'spicy')),
        ),
        Dessert: (
            ('sundae', ('sweet',)),
            ('churro', ('fried', 'sweet')),
        )
    }
    def setUp(self):
        Tag.create_table(True)
        Appetizer.create_table(True)
        Entree.create_table(True)
        Dessert.create_table(True)

    def tearDown(self):
        Tag.drop_table()
        Appetizer.drop_table()
        Entree.drop_table()
        Dessert.drop_table()

    def create(self):
        for model, foods in self.data.items():
            for name, tags in foods:
                inst = model.create(name=name)
                for tag in tags:
                    inst.add_tag(tag)

    def test_creation(self):
        t = Tag.create(tag='a tag')
        t.object = t
        t.save()

        t_db = Tag.get(Tag.id == t.id)
        self.assertEqual(t_db.object_id, t_db.get_id())
        self.assertEqual(t_db.object_type, 'tag')
        self.assertEqual(t_db.object, t_db)

    def test_gfk_api(self):
        self.create()

        # test instance api
        for model, foods in self.data.items():
            for food, tags in foods:
                inst = model.get(model.name == food)
                self.assertEqual([t.tag for t in inst.tags], list(tags))

        # test class api and ``object`` api
        apps_tags = [(t.tag, t.object.name) for t in Appetizer.tags.order_by(Tag.id)]
        data_tags = []
        for food, tags in self.data[Appetizer]:
            for t in tags:
                data_tags.append((t, food))

        self.assertEqual(apps_tags, data_tags)

    def test_missing(self):
        t = Tag.create(tag='sour')
        self.assertEqual(t.object, None)

        t.object_type = 'appetizer'
        t.object_id = 1
        # accessing the descriptor will raise a DoesNotExist
        self.assertRaises(Appetizer.DoesNotExist, getattr, t, 'object')

        t.object_type = 'unknown'
        t.object_id = 1
        self.assertRaises(AttributeError, getattr, t, 'object')

    def test_set_reverse(self):
        # assign query
        e = Entree.create(name='phad thai')
        s = Tag.create(tag='spicy')
        p = Tag.create(tag='peanuts')
        t = Tag.create(tag='thai')
        b = Tag.create(tag='beverage')

        e.tags = Tag.select().where(Tag.tag != 'beverage')
        self.assertEqual([t.tag for t in e.tags], ['peanuts', 'spicy', 'thai'])

        e = Entree.create(name='panang curry')
        c = Tag.create(tag='coconut')

        e.tags = [p, t, c, s]
        self.assertEqual([t.tag for t in e.tags], ['coconut', 'peanuts', 'spicy', 'thai'])
