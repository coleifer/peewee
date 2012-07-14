from hashlib import sha1 as _sha1
import sqlite3
import unittest

from peewee import *
import signals
import sqlite_ext as sqe
import sweepea


db = SqliteDatabase(':memory:')

class BaseSignalModel(signals.Model):
    class Meta:
        database = db

class ModelA(BaseSignalModel):
    a = CharField(default='')

class ModelB(BaseSignalModel):
    b = CharField(default='')

class BaseSweepeaModel(sweepea.Model):
    class Meta:
        database = db

class SModelA(BaseSweepeaModel):
    a1 = CharField()
    a2 = IntegerField()

class SModelB(BaseSweepeaModel):
    a = ForeignKeyField(SModelA)
    b1 = CharField()
    b2 = BooleanField()

class SModelC(BaseSweepeaModel):
    b = ForeignKeyField(SModelB)
    c1 = CharField()

# use a disk-backed db since memory dbs only exist for a single connection and
# we need to share the db w/2 for the locking tests.  additionally, set the
# sqlite_busy_timeout to 100ms so when we test locking it doesn't take forever
ext_db = sqe.SqliteExtDatabase('tmp.db', timeout=.1)
ext_db.adapter.register_aggregate(sqe.WeightedAverage, 1, 'weighted_avg')
ext_db.adapter.register_aggregate(sqe.WeightedAverage, 2, 'weighted_avg2')
ext_db.adapter.register_collation(sqe.collate_reverse)
ext_db.adapter.register_function(sqe.sha1)
#ext_db.adapter.register_function(sqerank) # < auto register


class BaseExtModel(sqe.Model):
    class Meta:
        database = ext_db

class User(BaseExtModel):
    username = CharField()
    password = CharField(default='')

class Post(BaseExtModel):
    user = ForeignKeyField(User)
    message = TextField()

class FTSPost(Post, sqe.FTSModel):
    pass

class Values(BaseExtModel):
    klass = IntegerField()
    value = FloatField()
    weight = FloatField()


class SqliteExtTestCase(unittest.TestCase):
    messages = [
        'A faith is a necessity to a man. Woe to him who believes in nothing.',
        'All who call on God in true faith, earnestly from the heart, will certainly be heard, and will receive what they have asked and desired.',
        'Be faithful in small things because it is in them that your strength lies.',
        'Faith consists in believing when it is beyond the power of reason to believe.',
        'Faith has to do with things that are not seen and hope with things that are not at hand.',
    ]
    def setUp(self):
        FTSPost.drop_table(True)
        Post.drop_table(True)
        User.drop_table(True)
        Values.drop_table(True)
        Values.create_table()
        User.create_table()
        Post.create_table()
        FTSPost.create_table(tokenize='porter', content_model=Post)

    def test_fts(self):
        u = User.create(username='u')
        posts = []
        for message in self.messages:
            posts.append(Post.create(user=u, message=message))

        pq = FTSPost.select().where(message__match='faith')
        self.assertEqual(list(pq), [])

        FTSPost.rebuild()
        FTSPost.optimize()

        # it will stem faithful -> faith b/c we use the porter tokenizer
        pq = FTSPost.select().where(message__match='faith').order_by('id')
        self.assertEqual([x.message for x in pq], self.messages)

        pq = FTSPost.select().where(message__match='believe').order_by('id')
        self.assertEqual([x.message for x in pq], [
            self.messages[0], self.messages[3],
        ])

        pq = FTSPost.select().where(message__match='thin*').order_by('id')
        self.assertEqual([x.message for x in pq], [
            self.messages[2], self.messages[4],
        ])

        pq = FTSPost.select().where(message__match='"it is"').order_by('id')
        self.assertEqual([x.message for x in pq], [
            self.messages[2], self.messages[3],
        ])

        pq = FTSPost.select(['*', sqe.Rank()]).where(message__match='things').order_by(('score', 'desc'))
        self.assertEqual([(x.message, x.score) for x in pq], [
            (self.messages[4], 2.0 / 3), (self.messages[2], 1.0 / 3),
        ])

        pq = FTSPost.select([sqe.Rank()]).where(message__match='faithful')
        self.assertEqual([x.score for x in pq], [.2] * 5)

    def test_custom_agg(self):
        data = (
            (1, 3.4, 1.0),
            (1, 6.4, 2.3),
            (1, 4.3, 0.9),
            (2, 3.4, 1.4),
            (3, 2.7, 1.1),
            (3, 2.5, 1.1),
        )
        for klass, value, wt in data:
            Values.create(klass=klass, value=value, weight=wt)

        vq = Values.select(['klass', ('weighted_avg', 'value', 'wtavg'), ('avg', 'value', 'avg')]).group_by('klass')
        q_data = [(v.klass, v.wtavg, v.avg) for v in vq]
        self.assertEqual(q_data, [
            (1, 4.7, 4.7),
            (2, 3.4, 3.4),
            (3, 2.6, 2.6),
        ])

        vq = Values.select(['klass', ('weighted_avg2', 'value, weight', 'wtavg'), ('avg', 'value', 'avg')]).group_by('klass')
        q_data = [(v.klass, str(v.wtavg)[:4], v.avg) for v in vq]
        self.assertEqual(q_data, [
            (1, '5.23', 4.7),
            (2, '3.4', 3.4),
            (3, '2.6', 2.6),
        ])

    def test_custom_collation(self):
        data = (
            ('u1', 'u2', 'u3'),
            (('p11', 'p12'), ('p21', 'p22', 'p23'), ()),
        )
        for user, posts in zip(data[0], data[1]):
            u = User.create(username=user)
            for p in posts:
                Post.create(user=u, message=p)

        uq = User.select().order_by('username collate collate_reverse')
        self.assertEqual([u.username for u in uq], ['u3', 'u2', 'u1'])

    def test_custom_function(self):
        s = lambda s: _sha1(s).hexdigest()
        u1 = User.create(username='u1', password=s('p1'))
        u2 = User.create(username='u2', password=s('p2'))

        uq = User.select().where(password=R('sha1(%s)', 'p2'))
        self.assertEqual(uq.get(), u2)

        uq = User.select().where(password=R('sha1(%s)', 'p1'))
        self.assertEqual(uq.get(), u1)

        uq = User.select().where(password=R('sha1(%s)', 'p3'))
        self.assertEqual(uq.count(), 0)

    def test_granular_transaction(self):
        conn = ext_db.get_conn()

        def test_locked_dbw(lt):
            with ext_db.granular_transaction(lt):
                User.create(username='u1', password='')
                conn2 = ext_db.adapter.connect(ext_db.database, **ext_db.connect_kwargs)
                conn2.execute('insert into user (username, password) values (?, ?);', ('x1', ''))
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'exclusive')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'immediate')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'deferred')

        def test_locked_dbr(lt):
            with ext_db.granular_transaction(lt):
                User.create(username='u1', password='')
                conn2 = ext_db.adapter.connect(ext_db.database, **ext_db.connect_kwargs)
                res = conn2.execute('select username from user')
                return res.fetchall()

        # no read-only stuff with exclusive locks
        self.assertRaises(sqlite3.OperationalError, test_locked_dbr, 'exclusive')

        # ok to do readonly w/immediate and deferred
        self.assertEqual(test_locked_dbr('immediate'), [])
        self.assertEqual(test_locked_dbr('deferred'), [('u1',)])

        # test everything by hand, by setting the default connection to 'exclusive'
        # and turning off autocommit behavior
        ext_db.set_autocommit(False)
        conn.isolation_level = 'exclusive'
        User.create(username='u2', password='') # <-- uncommitted

        # now, open a second connection w/exclusive and try to read, it will
        # be locked
        conn2 = ext_db.adapter.connect(ext_db.database, **ext_db.connect_kwargs)
        conn2.isolation_level = 'exclusive'
        self.assertRaises(sqlite3.OperationalError, conn2.execute, 'select * from user')

        # rollback the first connection's transaction, releasing the exclusive lock
        conn.rollback()
        ext_db.set_autocommit(True)

        with ext_db.granular_transaction('deferred'):
            User.create(username='u3', password='')

        res = conn2.execute('select username from user order by username;')
        self.assertEqual(res.fetchall(), [('u1',), ('u1',), ('u3',)])


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
        self.assertEqual(state, [(ModelA, '')])

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
