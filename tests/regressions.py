import datetime
import json
import random
import sys
import threading
import time
import uuid

from peewee import *
from playhouse.hybrid import *
from playhouse.migrate import migrate
from playhouse.migrate import SchemaMigrator

from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_MYSQL_ADVANCED_FEATURES
from .base import IS_SQLITE
from .base import IS_SQLITE_OLD
from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_mysql
from .base import requires_postgresql
from .base import skip_if
from .base import skip_unless
from .base import slow_test
from .base_models import Sample
from .base_models import Tweet
from .base_models import User


class ColAlias(TestModel):
    name = TextField(column_name='pname')


class CARef(TestModel):
    colalias = ForeignKeyField(ColAlias, backref='carefs', column_name='ca',
                               object_id_name='colalias_id')


class TestQueryAliasToColumnName(ModelTestCase):
    requires = [ColAlias, CARef]

    def setUp(self):
        super(TestQueryAliasToColumnName, self).setUp()
        with self.database.atomic():
            for name in ('huey', 'mickey'):
                col_alias = ColAlias.create(name=name)
                CARef.create(colalias=col_alias)

    def test_alias_to_column_name(self):
        # The issue here occurs when we take a field whose name differs from
        # it's underlying column name, then alias that field to it's column
        # name. In this case, peewee was *not* respecting the alias and using
        # the field name instead.
        query = (ColAlias
                 .select(ColAlias.name.alias('pname'))
                 .order_by(ColAlias.name))
        self.assertEqual([c.pname for c in query], ['huey', 'mickey'])

        # Ensure that when using dicts the logic is preserved.
        query = query.dicts()
        self.assertEqual([r['pname'] for r in query], ['huey', 'mickey'])

    def test_alias_overlap_with_join(self):
        query = (CARef
                 .select(CARef, ColAlias.name.alias('pname'))
                 .join(ColAlias)
                 .order_by(ColAlias.name))
        with self.assertQueryCount(1):
            self.assertEqual([r.colalias.pname for r in query],
                             ['huey', 'mickey'])

        # Note: we cannot alias the join to "ca", as this is the object-id
        # descriptor name.
        query = (CARef
                 .select(CARef, ColAlias.name.alias('pname'))
                 .join(ColAlias,
                       on=(CARef.colalias == ColAlias.id).alias('ca'))
                 .order_by(ColAlias.name))
        with self.assertQueryCount(1):
            self.assertEqual([r.ca.pname for r in query], ['huey', 'mickey'])

    def test_cannot_alias_join_to_object_id_name(self):
        query = CARef.select(CARef, ColAlias.name.alias('pname'))
        expr = (CARef.colalias == ColAlias.id).alias('colalias_id')
        self.assertRaises(ValueError, query.join, ColAlias, on=expr)


class TestOverrideModelRepr(BaseTestCase):
    def test_custom_reprs(self):
        # In 3.5.0, Peewee included a new implementation and semantics for
        # customizing model reprs. This introduced a regression where model
        # classes that defined a __repr__() method had this override ignored
        # silently. This test ensures that it is possible to completely
        # override the model repr.
        class Foo(Model):
            def __repr__(self):
                return 'FOO: %s' % self.id

        f = Foo(id=1337)
        self.assertEqual(repr(f), 'FOO: 1337')


class DiA(TestModel):
    a = TextField(unique=True)
class DiB(TestModel):
    a = ForeignKeyField(DiA)
    b = TextField()
class DiC(TestModel):
    b = ForeignKeyField(DiB)
    c = TextField()
class DiD(TestModel):
    c = ForeignKeyField(DiC)
    d = TextField()
class DiBA(TestModel):
    a = ForeignKeyField(DiA, to_field=DiA.a)
    b = TextField()


class TestDeleteInstanceRegression(ModelTestCase):
    database = get_in_memory_db()
    requires = [DiA, DiB, DiC, DiD, DiBA]

    def test_delete_instance_regression(self):
        with self.database.atomic():
            a1, a2, a3 = [DiA.create(a=a) for a in ('a1', 'a2', 'a3')]
            for a in (a1, a2, a3):
                for j in (1, 2):
                    b = DiB.create(a=a, b='%s-b%s' % (a.a, j))
                    c = DiC.create(b=b, c='%s-c' % (b.b))
                    d = DiD.create(c=c, d='%s-d' % (c.c))

                    DiBA.create(a=a, b='%s-b%s' % (a.a, j))

        # (a1 (b1 (c (d))), (b2 (c (d)))), (a2 ...), (a3 ...)
        with self.assertQueryCount(5):
            a2.delete_instance(recursive=True)

        queries = [logrecord.msg for logrecord in self._qh.queries[-5:]]
        self.assertEqual(sorted(queries, reverse=True), [
            ('DELETE FROM "di_d" WHERE ("di_d"."c_id" IN ('
             'SELECT "t1"."id" FROM "di_c" AS "t1" WHERE ("t1"."b_id" IN ('
             'SELECT "t2"."id" FROM "di_b" AS "t2" WHERE ("t2"."a_id" = ?)'
             '))))', [2]),
            ('DELETE FROM "di_c" WHERE ("di_c"."b_id" IN ('
             'SELECT "t1"."id" FROM "di_b" AS "t1" WHERE ("t1"."a_id" = ?)'
             '))', [2]),
            ('DELETE FROM "di_ba" WHERE ("di_ba"."a_id" = ?)', ['a2']),
            ('DELETE FROM "di_b" WHERE ("di_b"."a_id" = ?)', [2]),
            ('DELETE FROM "di_a" WHERE ("di_a"."id" = ?)', [2])
        ])

        # a1 & a3 exist, plus their relations.
        self.assertTrue(DiA.select().count(), 2)
        for rel in (DiB, DiBA, DiC, DiD):
            self.assertTrue(rel.select().count(), 4)  # 2x2

        with self.assertQueryCount(5):
            a1.delete_instance(recursive=True)

        # Only the objects related to a3 exist still.
        self.assertTrue(DiA.select().count(), 1)
        self.assertEqual(DiA.get(DiA.a == 'a3').id, a3.id)
        self.assertEqual([d.d for d in DiD.select().order_by(DiD.d)],
                         ['a3-b1-c-d', 'a3-b2-c-d'])
        self.assertEqual([c.c for c in DiC.select().order_by(DiC.c)],
                         ['a3-b1-c', 'a3-b2-c'])
        self.assertEqual([b.b for b in DiB.select().order_by(DiB.b)],
                         ['a3-b1', 'a3-b2'])
        self.assertEqual([ba.b for ba in DiBA.select().order_by(DiBA.b)],
                         ['a3-b1', 'a3-b2'])


class TestCountUnionRegression(ModelTestCase):
    @requires_mysql
    @requires_models(User)
    def test_count_union(self):
        with self.database.atomic():
            for i in range(5):
                User.create(username='user-%d' % i)

        lhs = User.select()
        rhs = User.select()
        query = (lhs | rhs)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'UNION '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2"'), [])

        self.assertEqual(query.count(), 5)

        query = query.limit(3)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'UNION '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2" '
            'LIMIT ?'), [3])
        self.assertEqual(query.count(), 3)


class User2(TestModel):
    username = TextField()

class Category2(TestModel):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)
    user = ForeignKeyField(User2)


class TestGithub1354(ModelTestCase):
    @requires_models(Category2, User2)
    def test_get_or_create_self_referential_fk2(self):
        huey = User2.create(username='huey')
        parent = Category2.create(name='parent', user=huey)
        child, created = Category2.get_or_create(parent=parent, name='child',
                                                 user=huey)
        child_db = Category2.get(Category2.parent == parent)
        self.assertEqual(child_db.user.username, 'huey')
        self.assertEqual(child_db.parent.name, 'parent')
        self.assertEqual(child_db.name, 'child')


class TestInsertFromSQL(ModelTestCase):
    def setUp(self):
        super(TestInsertFromSQL, self).setUp()

        self.database.execute_sql('create table if not exists user_src '
                                  '(name TEXT);')
        tbl = Table('user_src').bind(self.database)
        tbl.insert(name='foo').execute()

    def tearDown(self):
        super(TestInsertFromSQL, self).tearDown()
        self.database.execute_sql('drop table if exists user_src')

    @requires_models(User)
    def test_insert_from_sql(self):
        query_src = SQL('SELECT name FROM user_src')
        User.insert_from(query=query_src, fields=[User.username]).execute()
        self.assertEqual([u.username for u in User.select()], ['foo'])


class TestSubqueryFunctionCall(BaseTestCase):
    def test_subquery_function_call(self):
        Sample = Table('sample')
        SA = Sample.alias('s2')
        query = (Sample
                 .select(Sample.c.data)
                 .where(~fn.EXISTS(
                     SA.select(SQL('1')).where(SA.c.key == 'foo'))))
        self.assertSQL(query, (
            'SELECT "t1"."data" FROM "sample" AS "t1" '
            'WHERE NOT EXISTS('
            'SELECT 1 FROM "sample" AS "s2" WHERE ("s2"."key" = ?))'), ['foo'])


class A(TestModel):
    id = IntegerField(primary_key=True)
class B(TestModel):
    id = IntegerField(primary_key=True)
class C(TestModel):
    id = IntegerField(primary_key=True)
    a = ForeignKeyField(A)
    b = ForeignKeyField(B)

class TestCrossJoin(ModelTestCase):
    requires = [A, B, C]

    def setUp(self):
        super(TestCrossJoin, self).setUp()
        A.insert_many([(1,), (2,), (3,)], fields=[A.id]).execute()
        B.insert_many([(1,), (2,)], fields=[B.id]).execute()
        C.insert_many([
            (1, 1, 1),
            (2, 1, 2),
            (3, 2, 1)], fields=[C.id, C.a, C.b]).execute()

    def test_cross_join(self):
        query = (A
                 .select(A.id.alias('aid'), B.id.alias('bid'))
                 .join(B, JOIN.CROSS)
                 .join(C, JOIN.LEFT_OUTER, on=(
                     (C.a == A.id) &
                     (C.b == B.id)))
                 .where(C.id.is_null())
                 .order_by(A.id, B.id))
        self.assertEqual(list(query.tuples()), [(2, 2), (3, 1), (3, 2)])


def _create_users_tweets(db):
    data = (
        ('huey', ('meow', 'hiss', 'purr')),
        ('mickey', ('woof', 'bark')),
        ('zaizee', ()))
    with db.atomic():
        for username, tweets in data:
            user = User.create(username=username)
            for tweet in tweets:
                Tweet.create(user=user, content=tweet)


class TestSubqueryInSelect(ModelTestCase):
    requires = [User, Tweet]

    def setUp(self):
        super(TestSubqueryInSelect, self).setUp()
        _create_users_tweets(self.database)

    def test_subquery_in_select(self):
        subq = User.select().where(User.username == 'huey')
        query = (Tweet
                 .select(Tweet.content, Tweet.user.in_(subq).alias('is_huey'))
                 .order_by(Tweet.content))
        self.assertEqual([(r.content, r.is_huey) for r in query], [
            ('bark', False),
            ('hiss', True),
            ('meow', True),
            ('purr', True),
            ('woof', False)])


@requires_postgresql
class TestReturningIntegrationRegressions(ModelTestCase):
    requires = [User, Tweet]

    def test_returning_integration_subqueries(self):
        _create_users_tweets(self.database)

        # We can use a correlated subquery in the RETURNING clause.
        subq = (Tweet
                .select(fn.COUNT(Tweet.id).alias('ct'))
                .where(Tweet.user == User.id))
        query = (User
                 .update(username=(User.username + '-x'))
                 .returning(subq.alias('ct'), User.username))
        result = query.execute()
        self.assertEqual(sorted([(r.ct, r.username) for r in result]), [
            (0, 'zaizee-x'), (2, 'mickey-x'), (3, 'huey-x')])

        # We can use a correlated subquery via UPDATE...FROM, and reference the
        # FROM table in both the update and the RETURNING clause.
        subq = (User
                .select(User.id, fn.COUNT(Tweet.id).alias('ct'))
                .join(Tweet, JOIN.LEFT_OUTER)
                .group_by(User.id))
        query = (User
                 .update(username=User.username + subq.c.ct)
                 .from_(subq)
                 .where(User.id == subq.c.id)
                 .returning(subq.c.ct, User.username))
        result = query.execute()
        self.assertEqual(sorted([(r.ct, r.username) for r in result]), [
            (0, 'zaizee-x0'), (2, 'mickey-x2'), (3, 'huey-x3')])

    def test_returning_integration(self):
        query = (User
                 .insert_many([('huey',), ('mickey',), ('zaizee',)],
                              fields=[User.username])
                 .returning(User.id, User.username)
                 .objects())
        result = query.execute()
        self.assertEqual([(r.id, r.username) for r in result], [
            (1, 'huey'), (2, 'mickey'), (3, 'zaizee')])

        query = (User
                 .delete()
                 .where(~User.username.startswith('h'))
                 .returning(User.id, User.username)
                 .objects())
        result = query.execute()
        self.assertEqual(sorted([(r.id, r.username) for r in result]), [
            (2, 'mickey'), (3, 'zaizee')])


class TestUpdateIntegrationRegressions(ModelTestCase):
    requires = [User, Tweet, Sample]

    def setUp(self):
        super(TestUpdateIntegrationRegressions, self).setUp()
        _create_users_tweets(self.database)
        for i in range(4):
            Sample.create(counter=i, value=i)

    @skip_if(IS_MYSQL)
    def test_update_examples(self):
        # Do a simple update.
        res = (User
               .update(username=(User.username + '-cat'))
               .where(User.username != 'mickey')
               .execute())

        users = User.select().order_by(User.username)
        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat', 'mickey', 'zaizee-cat'])

        # Do an update using a subquery..
        subq = User.select(User.username).where(User.username == 'mickey')
        res = (User
               .update(username=(User.username + '-dog'))
               .where(User.username.in_(subq))
               .execute())
        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat', 'mickey-dog', 'zaizee-cat'])

        # Subquery referring to a different table.
        subq = User.select().where(User.username == 'mickey-dog')
        res = (Tweet
               .update(content=(Tweet.content + '-x'))
               .where(Tweet.user.in_(subq))
               .execute())

        self.assertEqual(
            [t.content for t in Tweet.select().order_by(Tweet.id)],
            ['meow', 'hiss', 'purr', 'woof-x', 'bark-x'])

        # Subquery on the right-hand of the assignment.
        subq = (Tweet
                .select(fn.COUNT(Tweet.id).cast('text'))
                .where(Tweet.user == User.id))
        res = User.update(username=(User.username + '-' + subq)).execute()

        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat-3', 'mickey-dog-2', 'zaizee-cat-0'])

    def test_update_examples_2(self):
        SA = Sample.alias()
        subq = (SA
                .select(SA.value)
                .where(SA.value.in_([1.0, 3.0])))
        res = (Sample
               .update(counter=(Sample.counter + Sample.value.cast('int')))
               .where(Sample.value.in_(subq))
               .execute())

        query = (Sample
                 .select(Sample.counter, Sample.value)
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query.clone()), [(0, 0.), (2, 1.), (2, 2.),
                                               (6, 3.)])

        subq = (SA
                .select(SA.counter - SA.value.cast('int'))
                .where(SA.value == Sample.value))
        res = (Sample
               .update(counter=subq)
               .where(Sample.value.in_([1., 3.]))
               .execute())
        self.assertEqual(list(query.clone()), [(0, 0.), (1, 1.), (2, 2.),
                                               (3, 3.)])

class TestSelectValueConversion(ModelTestCase):
    requires = [User]

    @skip_if(IS_SQLITE_OLD or IS_MYSQL)
    def test_select_value_conversion(self):
        u1 = User.create(username='u1')
        cte = User.select(User.id.cast('text')).cte('tmp', columns=('id',))

        query = User.select(cte.c.id.alias('id')).with_cte(cte).from_(cte)
        u1_id, = [user.id for user in query]
        self.assertEqual(u1_id, u1.id)

        query2 = User.select(cte.c.id.coerce(False)).with_cte(cte).from_(cte)
        u1_id, = [user.id for user in query2]
        self.assertEqual(u1_id, str(u1.id))


class ConflictDetectedException(Exception): pass

class BaseVersionedModel(TestModel):
    version = IntegerField(default=1, index=True)

    def save_optimistic(self):
        if not self.id:
            # This is a new record, so the default logic is to perform an
            # INSERT. Ideally your model would also have a unique
            # constraint that made it impossible for two INSERTs to happen
            # at the same time.
            return self.save()

        # Update any data that has changed and bump the version counter.
        field_data = dict(self.__data__)
        current_version = field_data.pop('version', 1)
        self._populate_unsaved_relations(field_data)
        field_data = self._prune_fields(field_data, self.dirty_fields)
        if not field_data:
            raise ValueError('No changes have been made.')

        ModelClass = type(self)
        field_data['version'] = ModelClass.version + 1  # Atomic increment.

        query = ModelClass.update(**field_data).where(
            (ModelClass.version == current_version) &
            (ModelClass.id == self.id))
        if query.execute() == 0:
            # No rows were updated, indicating another process has saved
            # a new version. How you handle this situation is up to you,
            # but for simplicity I'm just raising an exception.
            raise ConflictDetectedException()
        else:
            # Increment local version to match what is now in the db.
            self.version += 1
            return True

class VUser(BaseVersionedModel):
    username = TextField()

class VTweet(BaseVersionedModel):
    user = ForeignKeyField(VUser, null=True)
    content = TextField()


class TestOptimisticLockingDemo(ModelTestCase):
    requires = [VUser, VTweet]

    def test_optimistic_locking(self):
        vu = VUser(username='u1')
        vu.save_optimistic()
        vt = VTweet(user=vu, content='t1')
        vt.save_optimistic()

        # Update the "vt" row in the db, which bumps the version counter.
        vt2 = VTweet.get(VTweet.id == vt.id)
        vt2.content = 't1-x'
        vt2.save_optimistic()

        # Since no data was modified, this returns a ValueError.
        self.assertRaises(ValueError, vt.save_optimistic)

        # If we do make an update and attempt to save, a conflict is detected.
        vt.content = 't1-y'
        self.assertRaises(ConflictDetectedException, vt.save_optimistic)
        self.assertEqual(vt.version, 1)

        vt_db = VTweet.get(VTweet.id == vt.id)
        self.assertEqual(vt_db.content, 't1-x')
        self.assertEqual(vt_db.version, 2)
        self.assertEqual(vt_db.user.username, 'u1')

    def test_optimistic_locking_populate_fks(self):
        vt = VTweet(content='t1')
        vt.save_optimistic()

        vu = VUser(username='u1')
        vt.user = vu

        vu.save_optimistic()
        vt.save_optimistic()
        vt_db = VTweet.get(VTweet.content == 't1')
        self.assertEqual(vt_db.version, 2)
        self.assertEqual(vt_db.user.username, 'u1')


class TS(TestModel):
    key = CharField(primary_key=True)
    timestamp = TimestampField(utc=True)


class TestZeroTimestamp(ModelTestCase):
    requires = [TS]

    def test_zero_timestamp(self):
        t0 = TS.create(key='t0', timestamp=0)
        t1 = TS.create(key='t1', timestamp=1)

        t0_db = TS.get(TS.key == 't0')
        self.assertEqual(t0_db.timestamp, datetime.datetime(1970, 1, 1))

        t1_db = TS.get(TS.key == 't1')
        self.assertEqual(t1_db.timestamp,
                         datetime.datetime(1970, 1, 1, 0, 0, 1))


class Player(TestModel):
    name = TextField()

class Game(TestModel):
    name = TextField()
    player = ForeignKeyField(Player)

class Score(TestModel):
    game = ForeignKeyField(Game)
    points = IntegerField()


class TestJoinSubqueryAggregateViaLeftOuter(ModelTestCase):
    requires = [Player, Game, Score]

    def test_join_subquery_aggregate_left_outer(self):
        with self.database.atomic():
            p1, p2 = [Player.create(name=name) for name in ('p1', 'p2')]
            games = []
            for p in (p1, p2):
                for gnum in (1, 2):
                    g = Game.create(name='%s-g%s' % (p.name, gnum), player=p)
                    games.append(g)

            score_list = (
                (10, 20, 30),
                (),
                (100, 110, 100),
                (50, 50))
            for g, plist in zip(games, score_list):
                for p in plist:
                    Score.create(game=g, points=p)

        subq = (Game
                .select(Game.player, fn.SUM(Score.points).alias('ptotal'),
                        fn.AVG(Score.points).alias('pavg'))
                .join(Score, JOIN.LEFT_OUTER)
                .group_by(Game.player))
        query = (Player
                 .select(Player, subq.c.ptotal, subq.c.pavg)
                 .join(subq, on=(Player.id == subq.c.player_id))
                 .order_by(Player.name))

        with self.assertQueryCount(1):
            results = [(p.name, p.game.ptotal, p.game.pavg) for p in query]

        self.assertEqual(results, [('p1', 60, 20), ('p2', 410, 82)])

        with self.assertQueryCount(1):
            obj_query = query.objects()
            results = [(p.name, p.ptotal, p.pavg) for p in obj_query]

        self.assertEqual(results, [('p1', 60, 20), ('p2', 410, 82)])


class Project(TestModel):
    name = TextField()

class Task(TestModel):
    name = TextField()
    project = ForeignKeyField(Project, backref='tasks')
    alt = ForeignKeyField(Project, backref='alt_tasks')


class TestModelGraphMultiFK(ModelTestCase):
    requires = [Project, Task]

    def test_model_graph_multi_fk(self):
        pa, pb, pc = [Project.create(name=name) for name in 'abc']
        t1 = Task.create(name='t1', project=pa, alt=pc)
        t2 = Task.create(name='t2', project=pb, alt=pb)

        P1 = Project.alias('p1')
        P2 = Project.alias('p2')
        LO = JOIN.LEFT_OUTER

        # Query using join expression.
        q1 = (Task
              .select(Task, P1, P2)
              .join_from(Task, P1, LO, on=(Task.project == P1.id))
              .join_from(Task, P2, LO, on=(Task.alt == P2.id))
              .order_by(Task.name))

        # Query specifying target field.
        q2 = (Task
              .select(Task, P1, P2)
              .join_from(Task, P1, LO, on=Task.project)
              .join_from(Task, P2, LO, on=Task.alt)
              .order_by(Task.name))

        # Query specifying with missing target field.
        q3 = (Task
              .select(Task, P1, P2)
              .join_from(Task, P1, LO)
              .join_from(Task, P2, LO, on=Task.alt)
              .order_by(Task.name))

        for query in (q1, q2, q3):
            with self.assertQueryCount(1):
                t1, t2 = list(query)
                self.assertEqual(t1.project.name, 'a')
                self.assertEqual(t1.alt.name, 'c')
                self.assertEqual(t2.project.name, 'b')
                self.assertEqual(t2.alt.name, 'b')


class TestBlobFieldContextRegression(BaseTestCase):
    def test_blob_field_context_regression(self):
        class A(Model):
            f = BlobField()

        orig = A.f._constructor
        db = get_in_memory_db()
        with db.bind_ctx([A]):
            self.assertTrue(A.f._constructor is db.get_binary_type())

        self.assertTrue(A.f._constructor is orig)


class Product(TestModel):
    id = CharField()
    color = CharField()
    class Meta:
        primary_key = CompositeKey('id', 'color')

class Sku(TestModel):
    upc = CharField(primary_key=True)
    product_id = CharField()
    color = CharField()
    class Meta:
        constraints = [SQL('FOREIGN KEY (product_id, color) REFERENCES '
                           'product(id, color)')]

    @hybrid_property
    def product(self):
        if not hasattr(self, '_product'):
            self._product = Product.get((Product.id == self.product_id) &
                                        (Product.color == self.color))
        return self._product

    @product.setter
    def product(self, obj):
        self._product = obj
        self.product_id = obj.id
        self.color = obj.color

    @product.expression
    def product(cls):
        return (Product.id == cls.product_id) & (Product.color == cls.color)


class TestFKCompositePK(ModelTestCase):
    requires = [Product, Sku]

    def test_fk_composite_pk_regression(self):
        Product.insert_many([
            (1, 'red'),
            (1, 'blue'),
            (2, 'red'),
            (2, 'green'),
            (3, 'white')]).execute()
        Sku.insert_many([
            ('1-red', 1, 'red'),
            ('1-blue', 1, 'blue'),
            ('2-red', 2, 'red'),
            ('2-green', 2, 'green'),
            ('3-white', 3, 'white')]).execute()

        query = (Product
                 .select(Product, Sku)
                 .join(Sku, on=Sku.product)
                 .where(Product.color == 'red')
                 .order_by(Product.id, Product.color))
        with self.assertQueryCount(1):
            rows = [(p.id, p.color, p.sku.upc) for p in query]
            self.assertEqual(rows, [
                ('1', 'red', '1-red'),
                ('2', 'red', '2-red')])

        query = (Sku
                 .select(Sku, Product)
                 .join(Product, on=Sku.product)
                 .where(Product.color != 'red')
                 .order_by(Sku.upc))
        with self.assertQueryCount(1):
            rows = [(s.upc, s.product_id, s.color,
                     s.product.id, s.product.color) for s in query]
            self.assertEqual(rows, [
                ('1-blue', '1', 'blue', '1', 'blue'),
                ('2-green', '2', 'green', '2', 'green'),
                ('3-white', '3', 'white', '3', 'white')])


class RS(TestModel):
    name = TextField()

class RD(TestModel):
    key = TextField()
    value = IntegerField()
    rs = ForeignKeyField(RS, backref='rds')

class RKV(TestModel):
    key = CharField(max_length=10)
    value = IntegerField()
    extra = IntegerField()
    class Meta:
        primary_key = CompositeKey('key', 'value')


class TestRegressionCountDistinct(ModelTestCase):
    @requires_models(RS, RD)
    def test_regression_count_distinct(self):
        rs = RS.create(name='rs')

        nums = [0, 1, 2, 3, 2, 1, 0]
        RD.insert_many([('k%s' % i, i, rs) for i in nums]).execute()

        query = RD.select(RD.key).distinct()
        self.assertEqual(query.count(), 4)

        # Try re-selecting using the id/key, which are all distinct.
        query = query.select(RD.id, RD.key)
        self.assertEqual(query.count(), 7)

        # Re-select the key/value, of which there are 4 distinct.
        query = query.select(RD.key, RD.value)
        self.assertEqual(query.count(), 4)

        query = rs.rds.select(RD.key).distinct()
        self.assertEqual(query.count(), 4)

        query = rs.rds.select(RD.key, RD.value).distinct()
        self.assertEqual(query.count(), 4)  # Was returning 7!

    @requires_models(RKV)
    def test_regression_count_distinct_cpk(self):
        RKV.insert_many([('k%s' % i, i, i) for i in range(5)]).execute()
        self.assertEqual(RKV.select().distinct().count(), 5)


class TestReselectModelRegression(ModelTestCase):
    requires = [User]

    def test_reselect_model_regression(self):
        u1, u2, u3 = [User.create(username='u%s' % i) for i in '123']

        query = User.select(User.username).order_by(User.username.desc())
        self.assertEqual(list(query.tuples()), [('u3',), ('u2',), ('u1',)])

        query = query.select(User)
        self.assertEqual(list(query.tuples()), [
            (u3.id, 'u3',),
            (u2.id, 'u2',),
            (u1.id, 'u1',)])


class TestJoinCorrelatedSubquery(ModelTestCase):
    requires = [User, Tweet]

    def test_join_correlated_subquery(self):
        for i in range(3):
            user = User.create(username='u%s' % i)
            for j in range(i + 1):
                Tweet.create(user=user, content='u%s-%s' % (i, j))

        UA = User.alias()
        subq = (UA
                .select(UA.username)
                .where(UA.username.in_(('u0', 'u2'))))

        query = (Tweet
                 .select(Tweet, User)
                 .join(User, on=(
                     (Tweet.user == User.id) &
                     (User.username.in_(subq))))
                 .order_by(Tweet.id))

        with self.assertQueryCount(1):
            data = [(t.content, t.user.username) for t in query]
            self.assertEqual(data, [
                ('u0-0', 'u0'),
                ('u2-0', 'u2'),
                ('u2-1', 'u2'),
                ('u2-2', 'u2')])


class RU(TestModel):
    username = TextField()


class Recipe(TestModel):
    name = TextField()
    created_by = ForeignKeyField(RU, backref='recipes')
    changed_by = ForeignKeyField(RU, backref='recipes_modified')


class TestMultiFKJoinRegression(ModelTestCase):
    requires = [RU, Recipe]

    def test_multi_fk_join_regression(self):
        u1, u2 = [RU.create(username=u) for u in ('u1', 'u2')]
        for (n, a, m) in (('r11', u1, u1), ('r12', u1, u2), ('r21', u2, u1)):
            Recipe.create(name=n, created_by=a, changed_by=m)

        Change = RU.alias()
        query = (Recipe
                 .select(Recipe, RU, Change)
                 .join(RU, on=(RU.id == Recipe.created_by).alias('a'))
                 .switch(Recipe)
                 .join(Change, on=(Change.id == Recipe.changed_by).alias('b'))
                 .order_by(Recipe.name))
        with self.assertQueryCount(1):
            data = [(r.name, r.a.username, r.b.username) for r in query]
            self.assertEqual(data, [
                ('r11', 'u1', 'u1'),
                ('r12', 'u1', 'u2'),
                ('r21', 'u2', 'u1')])


class TestCompoundExistsRegression(ModelTestCase):
    requires = [User]

    def test_compound_regressions_1961(self):
        UA = User.alias()
        cq = (User.select(User.id) | UA.select(UA.id))
        # Calling .exists() fails with AttributeError, no attribute "columns".
        self.assertFalse(cq.exists())
        self.assertEqual(cq.count(), 0)

        User.create(username='u1')
        self.assertTrue(cq.exists())
        self.assertEqual(cq.count(), 1)


class TestViewFieldMapping(ModelTestCase):
    requires = [User]

    def tearDown(self):
        try:
            self.execute('drop view user_testview_fm')
        except Exception as exc:
            pass
        super(TestViewFieldMapping, self).tearDown()

    def test_view_field_mapping(self):
        user = User.create(username='huey')
        self.execute('create view user_testview_fm as '
                     'select id, username from users')

        class View(User):
            class Meta:
                table_name = 'user_testview_fm'

        self.assertEqual([(v.id, v.username) for v in View.select()],
                         [(user.id, 'huey')])


class TC(TestModel):
    ifield = IntegerField()
    ffield = FloatField()
    cfield = TextField()
    tfield = TextField()


class TestTypeCoercion(ModelTestCase):
    requires = [TC]

    def test_type_coercion(self):
        t = TC.create(ifield='10', ffield='20.5', cfield=30, tfield=40)
        t_db = TC.get(TC.id == t.id)

        self.assertEqual(t_db.ifield, 10)
        self.assertEqual(t_db.ffield, 20.5)
        self.assertEqual(t_db.cfield, '30')
        self.assertEqual(t_db.tfield, '40')


class TestLikeColumnValue(ModelTestCase):
    requires = [User, Tweet]

    def test_like_column_value(self):
        # e.g., find all tweets that contain the users own username.
        u1, u2, u3 = [User.create(username='u%s' % i) for i in (1, 2, 3)]
        data = (
            (u1, ('nada', 'i am u1', 'u1 is my name')),
            (u2, ('nothing', 'he is u1')),
            (u3, ('she is u2', 'hey u3 is me', 'xx')))
        for user, tweets in data:
            Tweet.insert_many([(user, tweet) for tweet in tweets],
                              fields=[Tweet.user, Tweet.content]).execute()

        expressions = (
            (Tweet.content ** ('%' + User.username + '%')),
            Tweet.content.contains(User.username))

        for expr in expressions:
            query = (Tweet
                     .select(Tweet, User)
                     .join(User)
                     .where(expr)
                     .order_by(Tweet.id))

            self.assertEqual([(t.user.username, t.content) for t in query], [
                ('u1', 'i am u1'),
                ('u1', 'u1 is my name'),
                ('u3', 'hey u3 is me')])


class TestUnionParenthesesRegression(ModelTestCase):
    requires = [User]

    def test_union_parentheses_regression(self):
        ua, ub, uc = [User.create(username=u) for u in 'abc']
        lhs = User.select(User.id).where(User.username == 'a')
        rhs = User.select(User.id).where(User.username == 'c')
        union = lhs.union_all(rhs)
        self.assertEqual(sorted([u.id for u in union]), [ua.id, uc.id])

        query = User.select().where(User.id.in_(union)).order_by(User.id)
        self.assertEqual([u.username for u in query], ['a', 'c'])


class NoPK(TestModel):
    data = IntegerField()
    class Meta:
        primary_key = False


class TestNoPKHashRegression(ModelTestCase):
    requires = [NoPK]

    def test_no_pk_hash_regression(self):
        npk = NoPK.create(data=1)
        npk_db = NoPK.get(NoPK.data == 1)
        # When a model does not define a primary key, we cannot test equality.
        self.assertTrue(npk != npk_db)

        # Their hash is the same, though they are not equal.
        self.assertEqual(hash(npk), hash(npk_db))


class Site(TestModel):
    url = TextField()

class Page(TestModel):
    site = ForeignKeyField(Site, backref='pages')
    title = TextField()

class PageItem(TestModel):
    page = ForeignKeyField(Page, backref='items')
    content = TextField()


class TestModelFilterJoinOrdering(ModelTestCase):
    requires = [Site, Page, PageItem]

    def setUp(self):
        super(TestModelFilterJoinOrdering, self).setUp()
        with self.database.atomic():
            s1, s2 = [Site.create(url=s) for s in ('s1', 's2')]
            p11, p12, p21 = [Page.create(site=s, title=t) for s, t in
                             ((s1, 'p1-1'), (s1, 'p1-2'), (s2, 'p2-1'))]
            items = (
                (p11, 's1p1i1'),
                (p11, 's1p1i2'),
                (p11, 's1p1i3'),
                (p12, 's1p2i1'),
                (p21, 's2p1i1'))
            PageItem.insert_many(items).execute()

    def test_model_filter_join_ordering(self):
        q = PageItem.filter(page__site__url='s1').order_by(PageItem.content)
        self.assertSQL(q, (
            'SELECT "t1"."id", "t1"."page_id", "t1"."content" '
            'FROM "page_item" AS "t1" '
            'INNER JOIN "page" AS "t2" ON ("t1"."page_id" = "t2"."id") '
            'INNER JOIN "site" AS "t3" ON ("t2"."site_id" = "t3"."id") '
            'WHERE ("t3"."url" = ?) ORDER BY "t1"."content"'), ['s1'])

        def assertQ(q):
            with self.assertQueryCount(1):
                self.assertEqual([pi.content for pi in q],
                                 ['s1p1i1', 's1p1i2', 's1p1i3', 's1p2i1'])

        assertQ(q)

        sid = Site.get(Site.url == 's1').id
        q = (PageItem
             .filter(page__site__url='s1', page__site__id=sid)
             .order_by(PageItem.content))
        assertQ(q)

        q = (PageItem
             .filter(page__site__id=sid)
             .filter(page__site__url='s1')
             .order_by(PageItem.content))
        assertQ(q)

        q = (PageItem
             .filter(page__site__id=sid)
             .filter(DQ(page__title='p1-1') | DQ(page__title='p1-2'))
             .filter(page__site__url='s1')
             .order_by(PageItem.content))
        assertQ(q)


class JsonField(TextField):
    def db_value(self, value):
        return json.dumps(value) if value is not None else None
    def python_value(self, value):
        if value is not None:
            return json.loads(value)

class JM(TestModel):
    key = TextField()
    data = JsonField()


class TestListValueConversion(ModelTestCase):
    requires = [JM]

    def test_list_value_conversion(self):
        jm = JM.create(key='k1', data=['i0', 'i1'])
        jm.key = 'k1-x'
        jm.save()

        jm_db = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm_db.data, ['i0', 'i1'])

        JM.update(data=['i1', 'i2']).execute()
        jm_db = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm_db.data, ['i1', 'i2'])

        jm2 = JM.create(key='k2', data=['i3', 'i4'])

        jm_db.data = ['i1', 'i2', 'i3']
        jm2.data = ['i4', 'i5']

        JM.bulk_update([jm_db, jm2], fields=[JM.key, JM.data])

        jm = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm.data, ['i1', 'i2', 'i3'])
        jm2 = JM.get(JM.key == 'k2')
        self.assertEqual(jm2.data, ['i4', 'i5'])


class TestCountSubqueryEquals(ModelTestCase):
    requires = [User, Tweet]

    def test_count_subquery_equals(self):
        a, b, c = [User.create(username=u) for u in 'abc']
        Tweet.insert_many([(a, 'a1'), (b, 'b1')]).execute()

        subq = (Tweet
                .select(fn.COUNT(Tweet.id))
                .where(Tweet.user == User.id))
        query = User.select().where(subq == 0)
        self.assertEqual([u.username for u in query], ['c'])


class BoolModel(TestModel):
    key = TextField()
    active = BooleanField()


class TestBooleanCompare(ModelTestCase):
    requires = [BoolModel]

    def test_boolean_compare(self):
        b1 = BoolModel.create(key='b1', active=True)
        b2 = BoolModel.create(key='b2', active=False)

        expr2key = (
            ((BoolModel.active == True), 'b1'),
            ((BoolModel.active == False), 'b2'),
            ((BoolModel.active != True), 'b2'),
            ((BoolModel.active != False), 'b1'))
        for expr, key in expr2key:
            q = BoolModel.select().where(expr)
            self.assertEqual([b.key for b in q], [key])


class CPK(TestModel):
    name = TextField()

class CPKFK(TestModel):
    key = CharField()
    cpk = ForeignKeyField(CPK)
    class Meta:
        primary_key = CompositeKey('key', 'cpk')


class TestCompositePKwithFK(ModelTestCase):
    requires = [CPK, CPKFK]

    def test_composite_pk_with_fk(self):
        c1 = CPK.create(name='c1')
        c2 = CPK.create(name='c2')
        CPKFK.create(key='k1', cpk=c1)
        CPKFK.create(key='k2', cpk=c1)
        CPKFK.create(key='k3', cpk=c2)

        query = (CPKFK
                 .select(CPKFK.key, CPK)
                 .join(CPK)
                 .order_by(CPKFK.key, CPK.name))
        with self.assertQueryCount(1):
            self.assertEqual([(r.key, r.cpk.name) for r in query],
                             [('k1', 'c1'), ('k2', 'c1'), ('k3', 'c2')])


class TestChainWhere(ModelTestCase):
    requires = [User]

    def test_chain_where(self):
        for username in 'abcd':
            User.create(username=username)

        q = (User.select()
             .where(User.username != 'a')
             .where(User.username != 'd')
             .order_by(User.username))
        self.assertEqual([u.username for u in q], ['b', 'c'])

        q = (User.select()
             .where(User.username != 'a')
             .where(User.username != 'd')
             .where(User.username == 'b'))
        self.assertEqual([u.username for u in q], ['b'])


class BCUser(TestModel):
    username = CharField(unique=True)

class BCTweet(TestModel):
    user = ForeignKeyField(BCUser, field=BCUser.username)
    content = TextField()


class TestBulkCreateWithFK(ModelTestCase):
    @requires_models(BCUser, BCTweet)
    def test_bulk_create_with_fk(self):
        u1 = BCUser.create(username='u1')
        u2 = BCUser.create(username='u2')
        with self.assertQueryCount(1):
            BCTweet.bulk_create([
                BCTweet(user='u1', content='t%s' % i)
                for i in range(4)])

        self.assertEqual(BCTweet.select().where(BCTweet.user == 'u1').count(), 4)
        self.assertEqual(BCTweet.select().where(BCTweet.user != 'u1').count(), 0)

        u = BCUser(username='u3')
        t = BCTweet(user=u, content='tx')
        with self.assertQueryCount(2):
            BCUser.bulk_create([u])
            BCTweet.bulk_create([t])

        with self.assertQueryCount(1):
            t_db = (BCTweet
                    .select(BCTweet, BCUser)
                    .join(BCUser)
                    .where(BCUser.username == 'u3')
                    .get())
            self.assertEqual(t_db.content, 'tx')
            self.assertEqual(t_db.user.username, 'u3')

    @requires_postgresql
    @requires_models(User, Tweet)
    def test_bulk_create_related_objects(self):
        u = User(username='u1')
        t = Tweet(user=u, content='t1')
        with self.assertQueryCount(2):
            User.bulk_create([u])
            Tweet.bulk_create([t])

        with self.assertQueryCount(1):
            t_db = Tweet.select(Tweet, User).join(User).get()
            self.assertEqual(t_db.content, 't1')
            self.assertEqual(t_db.user.username, 'u1')


class UUIDReg(TestModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    key = TextField()

class CharPKKV(TestModel):
    id = CharField(primary_key=True)
    key = TextField()
    value = IntegerField(default=0)


class TestBulkUpdateNonIntegerPK(ModelTestCase):
    @skip_if(sys.version_info[0] == 2)
    @requires_models(UUIDReg)
    def test_bulk_update_uuid_pk(self):
        r1 = UUIDReg.create(key='k1')
        r2 = UUIDReg.create(key='k2')
        r1.key = 'k1-x'
        r2.key = 'k2-x'
        UUIDReg.bulk_update((r1, r2), (UUIDReg.key,))

        r1_db, r2_db = UUIDReg.select().order_by(UUIDReg.key)
        self.assertEqual(r1_db.key, 'k1-x')
        self.assertEqual(r2_db.key, 'k2-x')

    @requires_models(CharPKKV)
    def test_bulk_update_non_integer_pk(self):
        a, b, c = [CharPKKV.create(id=c, key='k%s' % c) for c in 'abc']
        a.key = 'ka-x'
        a.value = 1
        b.value = 2
        c.key = 'kc-x'
        c.value = 3
        CharPKKV.bulk_update((a, b, c), (CharPKKV.key, CharPKKV.value))

        data = list(CharPKKV.select().order_by(CharPKKV.id).tuples())
        self.assertEqual(data, [
            ('a', 'ka-x', 1),
            ('b', 'kb', 2),
            ('c', 'kc-x', 3)])


class TestSaveClearingPK(ModelTestCase):
    requires = [User, Tweet]

    def test_save_clear_pk(self):
        u = User.create(username='u1')
        t1 = Tweet.create(content='t1', user=u)
        orig_id, t1.id = t1.id, None
        t1.content = 't2'
        t1.save()
        self.assertTrue(t1.id is not None)
        self.assertTrue(t1.id != orig_id)
        tweets = [t.content for t in u.tweets.order_by(Tweet.id)]
        self.assertEqual(tweets, ['t1', 't2'])


class Bits(TestModel):
    b1 = BitField(default=1)
    b1_1 = b1.flag(1)
    b1_2 = b1.flag(2)

    b2 = BitField(default=0)
    b2_1 = b2.flag()
    b2_2 = b2.flag()


class TestBitFieldName(ModelTestCase):
    requires = [Bits]

    def assertBits(self, bf, expected):
        b1_1, b1_2, b2_1, b2_2 = expected
        self.assertEqual(bf.b1_1, b1_1)
        self.assertEqual(bf.b1_2, b1_2)
        self.assertEqual(bf.b2_1, b2_1)
        self.assertEqual(bf.b2_2, b2_2)

    def test_bit_field_name(self):
        bf = Bits.create()
        self.assertBits(bf, (True, False, False, False))

        bf.b1_1 = False
        bf.b1_2 = True
        bf.b2_1 = True
        bf.save()
        self.assertBits(bf, (False, True, True, False))

        bf = Bits.get(Bits.id == bf.id)
        self.assertBits(bf, (False, True, True, False))

        self.assertEqual(bf.b1, 2)
        self.assertEqual(bf.b2, 1)

        self.assertEqual(Bits.select().where(Bits.b1_2).count(), 1)
        self.assertEqual(Bits.select().where(Bits.b2_2).count(), 0)


class FKMA(TestModel):
    name = TextField()

class FKMB(TestModel):
    name = TextField()
    fkma = ForeignKeyField(FKMA, backref='fkmb_set', null=True)


class TestFKMigrationRegression(ModelTestCase):
    requires = [FKMA, FKMB]

    def test_fk_migration(self):
        migrator = SchemaMigrator.from_database(self.database)
        kw = {'legacy': True} if IS_SQLITE else {}
        migrate(migrator.drop_column(
            FKMB._meta.table_name,
            FKMB.fkma.column_name, **kw))

        migrate(migrator.add_column(
            FKMB._meta.table_name,
            FKMB.fkma.column_name,
            FKMB.fkma))

        fa = FKMA.create(name='fa')
        FKMB.create(name='fb', fkma=fa)
        obj = FKMB.select().first()
        self.assertEqual(obj.name, 'fb')


class ModelTypeField(CharField):
    def db_value(self, value):
        if value is not None:
            return value._meta.name
    def python_value(self, value):
        if value is not None:
            return {'user': User, 'tweet': Tweet}[value]


class MTF(TestModel):
    name = TextField()
    mtype = ModelTypeField()


class TestFieldValueRegression(ModelTestCase):
    requires = [MTF]

    def test_field_value_regression(self):
        u = MTF.create(name='user', mtype=User)
        u_db = MTF.get()

        self.assertEqual(u_db.name, 'user')
        self.assertTrue(u_db.mtype is User)


class NLM(TestModel):
    a = IntegerField()
    b = IntegerField()

class TestRegressionNodeListClone(ModelTestCase):
    requires = [NLM]

    def test_node_list_clone_expr(self):
        expr = (NLM.a + NLM.b)
        query = NLM.select(expr.alias('expr')).order_by(expr).distinct(expr)
        self.assertSQL(query, (
            'SELECT DISTINCT ON ("t1"."a" + "t1"."b") '
            '("t1"."a" + "t1"."b") AS "expr" '
            'FROM "nlm" AS "t1" '
            'ORDER BY ("t1"."a" + "t1"."b")'), [])


class LK(TestModel):
    key = TextField()

class TestLikeEscape(ModelTestCase):
    requires = [LK]

    def assertNames(self, expr, expected):
        query = LK.select().where(expr).order_by(LK.id)
        self.assertEqual([lk.key for lk in query], expected)

    def test_like_escape(self):
        names = ('foo', 'foo%', 'foo%bar', 'foo_bar', 'fooxba', 'fooba')
        LK.insert_many([(n,) for n in names]).execute()

        cases = (
            (LK.key.contains('bar'), ['foo%bar', 'foo_bar']),
            (LK.key.contains('%'), ['foo%', 'foo%bar']),
            (LK.key.contains('_'), ['foo_bar']),
            (LK.key.contains('o%b'), ['foo%bar']),
            (LK.key.startswith('foo%'), ['foo%', 'foo%bar']),
            (LK.key.startswith('foo_'), ['foo_bar']),
            (LK.key.startswith('bar'), []),
            (LK.key.endswith('ba'), ['fooxba', 'fooba']),
            (LK.key.endswith('_bar'), ['foo_bar']),
            (LK.key.endswith('fo'), []),
        )
        for expr, expected in cases:
            self.assertNames(expr, expected)

    def test_like_escape_backslash(self):
        names = ('foo_bar\\baz', 'bar\\', 'fbar\\baz', 'foo_bar')
        LK.insert_many([(n,) for n in names]).execute()

        cases = (
            (LK.key.contains('\\'), ['foo_bar\\baz', 'bar\\', 'fbar\\baz']),
            (LK.key.contains('_bar\\'), ['foo_bar\\baz']),
            (LK.key.contains('bar\\'), ['foo_bar\\baz', 'bar\\', 'fbar\\baz']),
        )
        for expr, expected in cases:
            self.assertNames(expr, expected)


class FKF_A(TestModel):
    key = CharField(max_length=16, unique=True)

class FKF_B(TestModel):
    fk_a_1 = ForeignKeyField(FKF_A, field='key')
    fk_a_2 = IntegerField()


class TestQueryWithModelInstanceParam(ModelTestCase):
    requires = [FKF_A, FKF_B]

    def test_query_with_model_instance_param(self):
        a1 = FKF_A.create(key='k1')
        a2 = FKF_A.create(key='k2')
        b1 = FKF_B.create(fk_a_1=a1, fk_a_2=a1)
        b2 = FKF_B.create(fk_a_1=a2, fk_a_2=a2)

        # Ensure that UPDATE works as expected as well.
        b1.save()

        # See also keys.TestFKtoNonPKField test, which replicates much of this.
        args = (b1.fk_a_1, b1.fk_a_1_id, a1, a1.key)
        for arg in args:
            query = FKF_B.select().where(FKF_B.fk_a_1 == arg)
            self.assertSQL(query, (
                'SELECT "t1"."id", "t1"."fk_a_1_id", "t1"."fk_a_2" '
                'FROM "fkf_b" AS "t1" '
                'WHERE ("t1"."fk_a_1_id" = ?)'), ['k1'])
            b1_db = query.get()
            self.assertEqual(b1_db.id, b1.id)

        # When we are handed a model instance and a conversion (an IntegerField
        # in this case), when the attempted conversion fails we fall back to
        # using the given model's primary-key.
        args = (b1.fk_a_2, a1, a1.id)
        for arg in args:
            query = FKF_B.select().where(FKF_B.fk_a_2 == arg)
            self.assertSQL(query, (
                'SELECT "t1"."id", "t1"."fk_a_1_id", "t1"."fk_a_2" '
                'FROM "fkf_b" AS "t1" '
                'WHERE ("t1"."fk_a_2" = ?)'), [a1.id])
            b1_db = query.get()
            self.assertEqual(b1_db.id, b1.id)


@skip_if(IS_SQLITE_OLD or IS_MYSQL)
class TestModelSelectFromSubquery(ModelTestCase):
    requires = [User]

    def test_model_select_from_subquery(self):
        for i in range(5):
            User.create(username='u%s' % i)

        UA = User.alias()
        subquery = (UA.select()
                    .where(UA.username.in_(('u0', 'u2', 'u4'))))

        cte = (ValuesList([('u0',), ('u4',)], columns=['username'])
               .cte('user_cte', columns=['username']))

        query = (User
                 .select(subquery.c.id, subquery.c.username)
                 .from_(subquery)
                 .join(cte, on=(subquery.c.username == cte.c.username))
                 .with_cte(cte)
                 .order_by(subquery.c.username.desc()))
        self.assertEqual([u.username for u in query], ['u4', 'u0'])
        self.assertTrue(isinstance(query[0], User))


class CharPK(TestModel):
    id = CharField(primary_key=True)
    name = CharField(unique=True)

    def __str__(self):
        return self.name

class CharFK(TestModel):
    id = IntegerField(primary_key=True)
    cpk = ForeignKeyField(CharPK, field=CharPK.name)


class TestModelConversionRegression(ModelTestCase):
    requires = [CharPK, CharFK]

    def test_model_conversion_regression(self):
        cpks = [CharPK.create(id=str(i), name='u%s' % i) for i in range(3)]

        query = CharPK.select().where(CharPK.id << cpks)
        self.assertEqual(sorted([c.id for c in query]), ['0', '1', '2'])

        query = CharPK.select().where(CharPK.id.in_(list(CharPK.select())))
        self.assertEqual(sorted([c.id for c in query]), ['0', '1', '2'])

    def test_model_conversion_fk_retained(self):
        cpks = [CharPK.create(id=str(i), name='u%s' % i) for i in range(3)]
        cfks = [CharFK.create(id=i + 1, cpk='u%s' % i) for i in range(3)]

        c0, c1, c2 = cpks
        query = CharFK.select().where(CharFK.cpk << [c0, c2])
        self.assertEqual(sorted([f.id for f in query]), [1, 3])


class FKN_A(TestModel): pass
class FKN_B(TestModel):
    a = ForeignKeyField(FKN_A, null=True)

class TestSetFKNull(ModelTestCase):
    requires = [FKN_A, FKN_B]

    def test_set_fk_null(self):
        a1 = FKN_A.create()
        a2 = FKN_A()
        b1 = FKN_B(a=a1)
        b2 = FKN_B(a=a2)

        self.assertTrue(b1.a is a1)
        self.assertTrue(b2.a is a2)
        b1.a = b2.a = None
        self.assertTrue(b1.a is None)
        self.assertTrue(b2.a is None)


class TestWeirdAliases(ModelTestCase):
    requires = [User]

    @skip_if(IS_MYSQL)  # mysql can't do anything normally.
    def test_weird_aliases(self):
        User.create(username='huey')
        def assertAlias(s, expected):
            query = User.select(s).dicts()
            row = query[0]
            self.assertEqual(list(row)[0], expected)

        # When we explicitly provide an alias, use that.
        assertAlias(User.username.alias('"username"'), '"username"')
        assertAlias(User.username.alias('(username)'), '(username)')
        assertAlias(User.username.alias('user(name)'), 'user(name)')
        assertAlias(User.username.alias('(username"'), '(username"')
        assertAlias(User.username.alias('"username)'), '"username)')
        assertAlias(fn.LOWER(User.username).alias('user (name)'), 'user (name)')

        # Here peewee cannot tell that an alias was given, so it will attempt
        # to clean-up the column name returned by the cursor description.
        assertAlias(SQL('"t1"."username" AS "user name"'), 'user name')
        assertAlias(SQL('"t1"."username" AS "user (name)"'), 'user (name')
        assertAlias(SQL('"t1"."username" AS "(username)"'), 'username')
        assertAlias(SQL('"t1"."username" AS "x.y.(username)"'), 'username')
        if IS_SQLITE:
            assertAlias(SQL('LOWER("t1"."username")'), 'username')



class NDF(TestModel):
    key = CharField(primary_key=True)
    date = DateTimeField(null=True)

class TestBulkUpdateAllNull(ModelTestCase):
    requires = [NDF]

    @skip_unless(IS_SQLITE or IS_MYSQL, 'postgres cannot do this properly')
    def test_bulk_update_all_null(self):
        n1 = NDF.create(key='n1', date=datetime.datetime(2021, 1, 1))
        n2 = NDF.create(key='n2', date=datetime.datetime(2021, 1, 2))
        rows = [NDF(key=key, date=None) for key in ('n1', 'n2')]
        NDF.bulk_update(rows, fields=['date'])

        query = NDF.select().order_by(NDF.key).tuples()
        self.assertEqual([r for r in query], [('n1', None), ('n2', None)])


class CQA(TestModel):
    a = TextField()
    b = TextField()


class TestSelectFromUnion(ModelTestCase):
    requires = [CQA]

    def test_select_from_union(self):
        CQA.insert_many([('a%d' % i, 'b%d' % i) for i in range(10)]).execute()

        q1 = CQA.select(CQA.a).order_by(CQA.id).limit(3)
        q2 = CQA.select(CQA.b).order_by(CQA.id).limit(3)

        wq1 = q1.select_from(SQL('*'))
        wq2 = q2.select_from(SQL('*'))
        union = wq1 | wq2
        data = [val for val, in union.tuples()]
        self.assertEqual(sorted(data), ['a0', 'a1', 'a2', 'b0', 'b1', 'b2'])


class DF(TestModel):
    name = TextField()
    value = IntegerField()
class DFC(TestModel):
    df = ForeignKeyField(DF)
    name = TextField()
    value = IntegerField()
class DFGC(TestModel):
    dfc = ForeignKeyField(DFC)
    name = TextField()
    value = IntegerField()


class TestDjangoFilterRegression(ModelTestCase):
    requires = [DF, DFC, DFGC]

    def test_django_filter_regression(self):
        a, b, c = [DF.create(name=n, value=i) for i, n in enumerate('abc')]
        ca1 = DFC.create(df=a, name='a1', value=11)
        ca2 = DFC.create(df=a, name='a2', value=12)
        cb1 = DFC.create(df=b, name='b1', value=21)

        gca1_1 = DFGC.create(dfc=ca1, name='a1-1', value=101)
        gca1_2 = DFGC.create(dfc=ca1, name='a1-2', value=101)
        gca2_1 = DFGC.create(dfc=ca2, name='a2-1', value=111)

        def assertNames(q, expected):
            self.assertEqual(sorted([n.name for n in q]), expected)

        assertNames(DF.filter(name='a'), ['a'])
        assertNames(DF.filter(name='a', id=a.id), ['a'])
        assertNames(DF.filter(name__in=['a', 'c']), ['a', 'c'])
        assertNames(DF.filter(name__in=['a', 'c'], id=a.id), ['a'])
        assertNames(DF.filter(dfc_set__name='a1'), ['a'])
        assertNames(DF.filter(dfc_set__name__in=['a1', 'b1']), ['a', 'b'])
        assertNames(DF.filter(DQ(dfc_set__name='a1') | DQ(dfc_set__name='b1')),
                    ['a', 'b'])
        assertNames(DF.filter(dfc_set__dfgc_set__name='a1-1'), ['a'])
        assertNames(DF.filter(
            DQ(dfc_set__dfgc_set__name='a1-1') |
            DQ(dfc_set__dfgc_set__name__in=['x', 'y'])), ['a'])

        assertNames(DFC.filter(df__name='a'), ['a1', 'a2'])
        assertNames(DFC.filter(df__name='a', value=11), ['a1'])
        assertNames(DFC.filter(DQ(df__name='a') | DQ(df__name='b')),
                    ['a1', 'a2', 'b1'])
        assertNames(DFC.filter(
            DQ(df__name='a') | DQ(dfgc_set__name='a1-1')).distinct(),
            ['a1', 'a2'])

        assertNames(DFGC.filter(dfc__df__name='a'), ['a1-1', 'a1-2', 'a2-1'])
        assertNames(DFGC.filter(dfc__df__name='a', dfc__name='a2'), ['a2-1'])
        assertNames(DFGC.filter(
            DQ(dfc__df__value__lte=0) |
            DQ(dfc__df__name='a', dfc__name='a1') |
            DQ(dfc__name='a2')), ['a1-1', 'a1-2', 'a2-1'])

        assertNames(
            (DFGC.filter(DQ(dfc__df__value__lte=10) | DQ(dfc__value__lte=101))
             .filter(DQ(name__ilike='a1%') | DQ(dfc__value=101))),
            ['a1-1', 'a1-2'])

        assertNames(DFGC.filter(dfc__df=a), ['a1-1', 'a1-2', 'a2-1'])
        assertNames(DFGC.filter(dfc__df=a.id), ['a1-1', 'a1-2', 'a2-1'])

        q = DFC.select().join(DF)
        assertNames(q.filter(df=a), ['a1', 'a2'])
        assertNames(q.filter(df__name='a'), ['a1', 'a2'])

        DFA = DF.alias()
        DFCA = DFC.alias()
        DFGCA = DFGC.alias()
        q = DFCA.select().join(DFA)
        assertNames(q.filter(df=a), ['a1', 'a2'])
        assertNames(q.filter(df__name='a'), ['a1', 'a2'])

        q = DFGC.select().join(DFC).join(DF)
        assertNames(q.filter(dfc__df=a), ['a1-1', 'a1-2', 'a2-1'])

        q = DFGCA.select().join(DFCA).join(DFA)
        assertNames(q.filter(dfc__df=a), ['a1-1', 'a1-2', 'a2-1'])

        q = DF.select().join(DFC).join(DFGC)
        assertNames(q.filter(dfc_set__dfgc_set__name='a1-1'), ['a'])


class TestFunctionInfiniteLoop(BaseTestCase):
    def test_function_infinite_loop(self):
        self.assertRaises(TypeError, lambda: list(fn.COUNT()))


class State(TestModel):
    name = TextField()
class Transition(TestModel):
    src = ForeignKeyField(State, backref='sources')
    dest = ForeignKeyField(State, backref='dests')

class TestJoinTypePrefetchMultipleFKs(ModelTestCase):
    requires = [State, Transition]

    def test_join_prefetch_multiple_fks(self):
        s1, s2a, s2b, s3 = [State.create(name=s)
                            for s in ('s1', 's2a', 's2b', 's3')]
        t1 = Transition.create(src=s1, dest=s2a)
        t2 = Transition.create(src=s1, dest=s2b)
        t3 = Transition.create(src=s2a, dest=s3)
        t4 = Transition.create(src=s2b, dest=s3)

        query = State.select().where(State.name != 's3').order_by(State.name)
        transitions = (Transition
                       .select(Transition, State)
                       .join(State, on=Transition.dest)
                       .order_by(Transition.id))
        with self.assertQueryCount(2):
            p = prefetch(query, transitions, prefetch_type=PREFETCH_TYPE.JOIN)
            accum = []
            for row in p:
                accum.append((row.name, row.sources, row.dests,
                              [d.dest.name for d in row.sources],
                              [d.src.name for d in row.dests]))

        self.assertEqual(accum, [
            ('s1', [t1, t2], [], ['s2a', 's2b'], []),
            ('s2a', [t3], [t1], ['s3'], ['s1']),
            ('s2b', [t4], [t2], ['s3'], ['s1'])])


@slow_test()
class TestThreadSafetyDecorators(ModelTestCase):
    requires = [User]

    def test_thread_safety_atomic(self):
        @self.database.atomic()
        def get_one(n):
            time.sleep(n)
            return User.select().first()
        def run(n):
            with self.database.atomic():
                get_one(n)
        User.create(username='u')
        threads = [threading.Thread(target=run, args=(i,))
                   for i in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.5)]
        for t in threads: t.start()
        for t in threads: t.join()
