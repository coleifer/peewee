import unittest

from peewee import *
import signals


db = SqliteDatabase(':memory:')

class BaseSignalModel(signals.Model):
    class Meta:
        database = db

class ModelA(BaseSignalModel):
    a = CharField()

class ModelB(BaseSignalModel):
    b = CharField()


class SignalsTestCase(unittest.TestCase):
    def setUp(self):
        ModelA.create_table(True)
        ModelB.create_table(True)

    def tearDown(self):
        ModelA.drop_table()
        ModelB.drop_table()
        signals.pre_save._flush()
        signals.post_save._flush()
        signals.pre_delete._flush()
        signals.post_delete._flush()
        signals.pre_init._flush()
        signals.post_init._flush()

    def test_pre_save(self):
        state = []

        @signals.connect(signals.pre_save)
        def pre_save(sender, instance, created):
            state.append((sender, instance, instance.get_pk(), created))
        m = ModelA()
        m.save()
        self.assertEqual(state, [(ModelA, m, None, True)])

        m.save()
        self.assertTrue(m.id is not None)
        self.assertEqual(state[-1], (ModelA, m, m.id, False))

    def test_post_save(self):
        state = []

        @signals.connect(signals.post_save)
        def post_save(sender, instance, created):
            state.append((sender, instance, instance.get_pk(), created))
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

        @signals.connect(signals.pre_delete)
        def pre_delete(sender, instance):
            state.append((sender, instance, ModelA.select().count()))
        m.delete_instance()
        self.assertEqual(state, [(ModelA, m, 1)])

    def test_post_delete(self):
        state = []

        m = ModelA()
        m.save()

        @signals.connect(signals.post_delete)
        def post_delete(sender, instance):
            state.append((sender, instance, ModelA.select().count()))
        m.delete_instance()
        self.assertEqual(state, [(ModelA, m, 0)])

    def test_pre_init(self):
        state = []

        m = ModelA(a='a')
        m.save()

        @signals.connect(signals.pre_init)
        def pre_init(sender, instance):
            state.append((sender, instance.a))

        ModelA.get()
        self.assertEqual(state, [(ModelA, None)])

    def test_post_init(self):
        state = []

        m = ModelA(a='a')
        m.save()

        @signals.connect(signals.post_init)
        def post_init(sender, instance):
            state.append((sender, instance.a))

        ModelA.get()
        self.assertEqual(state, [(ModelA, 'a')])

    def test_sender(self):
        state = []

        @signals.connect(signals.post_save, sender=ModelA)
        def post_save(sender, instance, created):
            state.append(instance)

        m = ModelA.create()
        self.assertEqual(state, [m])

        m2 = ModelB.create()
        self.assertEqual(state, [m])

    def test_connect_disconnect(self):
        state = []

        @signals.connect(signals.post_save, sender=ModelA)
        def post_save(sender, instance, created):
            state.append(instance)

        m = ModelA.create()
        self.assertEqual(state, [m])

        signals.post_save.disconnect(post_save)
        m2 = ModelA.create()
        self.assertEqual(state, [m])
