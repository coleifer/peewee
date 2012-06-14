import unittest

from peewee import *
import signals
import sweepea


db = SqliteDatabase(':memory:')

class BaseSignalModel(signals.Model):
    class Meta:
        database = db

class ModelA(BaseSignalModel):
    a = CharField()

class ModelB(BaseSignalModel):
    b = CharField()

class SModelA(sweepea.Model):
    a1 = CharField()
    a2 = IntegerField()

class SModelB(sweepea.Model):
    a = ForeignKeyField(SModelA)
    b1 = CharField()
    b2 = BooleanField()

class SModelC(sweepea.Model):
    b = ForeignKeyField(SModelB)
    c1 = CharField()


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


class SweepeaTestCase(unittest.TestCase):
    def setUp(self):
        SModelC.drop_table(True)
        SModelB.drop_table(True)
        SModelA.drop_table(True)
        SModelA.create_table()
        SModelB.create_table()
        SModelC.create_table()

        a1 = SModelA.create(a1='foo', a2=1)
        a2 = SModelA.create(a1='bar', a2=2)
        a3 = SModelA.create(a1='baz', a2=3)

        b1 = SModelB.create(a=a1, b1='herp', b2=True)
        b2 = SModelB.create(a=a2, b1='derp', b2=False)

        c1 = SModelC.create(b=b1, c1='hurr', c2=0)
        c2 = SModelC.create(b=b2, c1='durr', c2=1)

    def test_queries(self):
        sq = sweepea.T(SModelA).q().order_by('id')
        self.assertEqual([x.a1 for x in sq], ['foo', 'bar', 'baz'])

        t = (SModelB * SModelA) ** (SModelA.a1 == 'foo')
        self.assertEqual([x.b1 for x in t], ['herp'])

        t = (SModelA) ** (SModelA.a2 > 1) % SModelA.a1
        self.assertEqual([x.a1 for x in t], ['bar', 'baz'])

        t = (SModelA) ** (SModelA.a2 > 1) % (SModelA.a1) << -SModelA.id
        self.assertEqual([x.a1 for x in t], ['baz', 'bar'])

        t = (SModelC * SModelB * SModelA) ** (SModelB.b2 == True) % (SModelC.c1, SModelB.b1)
        self.assertEqual([(x.c1, x.b1) for x in t], [('hurr', 'herp')])
