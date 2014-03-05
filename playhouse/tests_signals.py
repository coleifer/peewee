import unittest

from peewee import *
from playhouse import signals


db = SqliteDatabase(':memory:')

class BaseSignalModel(signals.Model):
    class Meta:
        database = db

class ModelA(BaseSignalModel):
    a = CharField(default='')

class ModelB(BaseSignalModel):
    b = CharField(default='')

class SubclassOfModelB(ModelB):
    pass

class SignalsTestCase(unittest.TestCase):
    def setUp(self):
        ModelA.create_table(True)
        ModelB.create_table(True)
        SubclassOfModelB.create_table(True)

    def tearDown(self):
        ModelA.drop_table()
        ModelB.drop_table()
        SubclassOfModelB.drop_table()
        signals.pre_save._flush()
        signals.post_save._flush()
        signals.pre_delete._flush()
        signals.post_delete._flush()
        signals.pre_init._flush()
        signals.post_init._flush()

    def test_pre_save(self):
        state = []

        @signals.pre_save()
        def pre_save(sender, instance, created):
            state.append((sender, instance, instance.get_id(), created))
        m = ModelA()
        m.save()
        self.assertEqual(state, [(ModelA, m, None, True)])

        m.save()
        self.assertTrue(m.id is not None)
        self.assertEqual(state[-1], (ModelA, m, m.id, False))

    def test_post_save(self):
        state = []

        @signals.post_save()
        def post_save(sender, instance, created):
            state.append((sender, instance, instance.get_id(), created))
        m = ModelA()
        m.save()

        self.assertTrue(m.id is not None)
        self.assertEqual(state, [(ModelA, m, m.id, True)])

        m.save()
        self.assertEqual(state[-1], (ModelA, m, m.id, False))

    def test_pre_delete(self):
        state = []

        m = ModelA()
        m.save()

        @signals.pre_delete()
        def pre_delete(sender, instance):
            state.append((sender, instance, ModelA.select().count()))
        m.delete_instance()
        self.assertEqual(state, [(ModelA, m, 1)])

    def test_post_delete(self):
        state = []

        m = ModelA()
        m.save()

        @signals.post_delete()
        def post_delete(sender, instance):
            state.append((sender, instance, ModelA.select().count()))
        m.delete_instance()
        self.assertEqual(state, [(ModelA, m, 0)])

    def test_pre_init(self):
        state = []

        m = ModelA(a='a')
        m.save()

        @signals.pre_init()
        def pre_init(sender, instance):
            state.append((sender, instance.a))

        ModelA.get()
        self.assertEqual(state, [(ModelA, '')])

    def test_post_init(self):
        state = []

        m = ModelA(a='a')
        m.save()

        @signals.post_init()
        def post_init(sender, instance):
            state.append((sender, instance.a))

        ModelA.get()
        self.assertEqual(state, [(ModelA, 'a')])

    def test_sender(self):
        state = []

        @signals.post_save(sender=ModelA)
        def post_save(sender, instance, created):
            state.append(instance)

        m = ModelA.create()
        self.assertEqual(state, [m])

        m2 = ModelB.create()
        self.assertEqual(state, [m])

    def test_connect_disconnect(self):
        state = []

        @signals.post_save(sender=ModelA)
        def post_save(sender, instance, created):
            state.append(instance)

        m = ModelA.create()
        self.assertEqual(state, [m])

        signals.post_save.disconnect(post_save)
        m2 = ModelA.create()
        self.assertEqual(state, [m])

    def test_subclass_instance_receive_signals(self):
        state = []

        @signals.post_save(sender=ModelB)
        def post_save(sender, instance, created):
            state.append(instance)

        m = SubclassOfModelB.create()
        assert m in state
