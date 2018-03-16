from peewee import *
from playhouse import signals

from .base import get_in_memory_db
from .base import ModelTestCase


class BaseSignalModel(signals.Model):
    pass

class A(BaseSignalModel):
    a = TextField(default='')

class B(BaseSignalModel):
    b = TextField(default='')

class SubB(B): pass


class TestSignals(ModelTestCase):
    database = get_in_memory_db()
    requires = [A, B, SubB]

    def tearDown(self):
        super(TestSignals, self).tearDown()
        signals.pre_save._flush()
        signals.post_save._flush()
        signals.pre_delete._flush()
        signals.post_delete._flush()
        signals.pre_init._flush()

    def test_pre_save(self):
        state = []
        @signals.pre_save()
        def pre_save(sender, instance, created):
            state.append((sender, instance, instance._pk, created))

        a = A()
        self.assertEqual(a.save(), 1)
        self.assertEqual(state, [(A, a, None, True)])

        self.assertEqual(a.save(), 1)
        self.assertTrue(a.id is not None)
        self.assertEqual(len(state), 2)
        self.assertEqual(state[-1], (A, a, a.id, False))

    def test_post_save(self):
        state = []
        @signals.post_save()
        def post_save(sender, instance, created):
            state.append((sender, instance, instance._pk, created))
        a = A()
        a.save()

        self.assertTrue(a.id is not None)
        self.assertEqual(state, [(A, a, a.id, True)])

        a.save()
        self.assertEqual(len(state), 2)
        self.assertEqual(state[-1], (A, a, a.id, False))

    def test_pre_delete(self):
        state = []
        @signals.pre_delete()
        def pre_delete(sender, instance):
            state.append((sender, instance, A.select().count()))

        a = A.create()
        self.assertEqual(a.delete_instance(), 1)
        self.assertEqual(state, [(A, a, 1)])

    def test_post_delete(self):
        state = []
        @signals.post_delete()
        def post_delete(sender, instance):
            state.append((sender, instance, A.select().count()))

        a = A.create()
        a.delete_instance()
        self.assertEqual(state, [(A, a, 0)])

    def test_pre_init(self):
        state = []
        A.create(a='a')

        @signals.pre_init()
        def pre_init(sender, instance):
            state.append((sender, instance.a))

        A.get()
        self.assertEqual(state, [(A, 'a')])

    def test_sender(self):
        state = []

        @signals.post_save(sender=A)
        def post_save(sender, instance, created):
            state.append(instance)

        m = A.create()
        self.assertEqual(state, [m])

        m2 = B.create()
        self.assertEqual(state, [m])

    def test_connect_disconnect(self):
        state = []

        @signals.post_save(sender=A)
        def post_save(sender, instance, created):
            state.append(instance)

        a = A.create()
        self.assertEqual(state, [a])

        # Signal was registered with a specific sender, so this fails.
        self.assertRaises(ValueError, signals.post_save.disconnect, post_save)

        # Disconnect signal, specifying sender.
        signals.post_save.disconnect(post_save, sender=A)

        # Signal handler has been unregistered.
        a2 = A.create()
        self.assertEqual(state, [a])

        # Re-connect without specifying sender.
        signals.post_save.connect(post_save)
        a3 = A.create()
        self.assertEqual(state, [a, a3])

        # Signal was not registered with a sender, so this fails.
        self.assertRaises(ValueError, signals.post_save.disconnect, post_save,
                          sender=A)
        signals.post_save.disconnect(post_save)

    def test_function_reuse(self):
        state = []

        @signals.post_save(sender=A)
        def post_save(sender, instance, created):
            state.append(instance)

        # Connect function for sender=B as well.
        signals.post_save(sender=B)(post_save)

        a = A.create()
        b = B.create()
        self.assertEqual(state, [a, b])

    def test_subclass_instance_receive_signals(self):
        state = []

        @signals.post_save(sender=B)
        def post_save(sender, instance, created):
            state.append(instance)

        b = SubB.create()
        assert b in state
