import itertools
import sys

from peewee import ModelQueryResultWrapper
from peewee import NaiveQueryResultWrapper
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import skip_test_if
from playhouse.tests.base import test_db
from playhouse.tests.models import *


class TestQueryResultWrapper(ModelTestCase):
    requires = [User, Blog, Comment]

    def test_iteration(self):
        User.create_users(10)
        with self.assertQueryCount(1):
            sq = User.select()
            qr = sq.execute()

            first_five = []
            for i, u in enumerate(qr):
                first_five.append(u.username)
                if i == 4:
                    break
            self.assertEqual(first_five, ['u1', 'u2', 'u3', 'u4', 'u5'])

            names = lambda it: [obj.username for obj in it]
            self.assertEqual(names(sq[5:]), ['u6', 'u7', 'u8', 'u9', 'u10'])
            self.assertEqual(names(sq[2:5]), ['u3', 'u4', 'u5'])

            another_iter = names(qr)
            self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

            another_iter = names(qr)
            self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

    def test_count(self):
        User.create_users(5)

        with self.assertQueryCount(1):
            query = User.select()
            qr = query.execute()
            self.assertEqual(qr.count, 5)

            # Calling again does not incur another query.
            self.assertEqual(qr.count, 5)

        with self.assertQueryCount(1):
            query = query.where(User.username != 'u1')
            qr = query.execute()
            self.assertEqual(qr.count, 4)

            # Calling again does not incur another query.
            self.assertEqual(qr.count, 4)

    def test_len(self):
        User.create_users(5)

        with self.assertQueryCount(1):
            query = User.select()
            self.assertEqual(len(query), 5)

            qr = query.execute()
            self.assertEqual(len(qr), 5)

        with self.assertQueryCount(1):
            query = query.where(User.username != 'u1')
            qr = query.execute()
            self.assertEqual(len(qr), 4)
            self.assertEqual(len(query), 4)

    def test_nested_iteration(self):
        User.create_users(4)
        with self.assertQueryCount(1):
            sq = User.select()
            outer = []
            inner = []
            for i_user in sq:
                outer.append(i_user.username)
                for o_user in sq:
                    inner.append(o_user.username)

            self.assertEqual(outer, ['u1', 'u2', 'u3', 'u4'])
            self.assertEqual(inner, ['u1', 'u2', 'u3', 'u4'] * 4)

    def test_iteration_protocol(self):
        User.create_users(3)

        with self.assertQueryCount(1):
            query = User.select().order_by(User.id)
            qr = query.execute()
            for _ in range(2):
                for user in qr:
                    pass

            i = iter(qr)
            for obj in i:
                pass
            self.assertRaises(StopIteration, next, i)
            self.assertEqual([u.username for u in qr], ['u1', 'u2', 'u3'])
            self.assertEqual(query[0].username, 'u1')
            self.assertEqual(query[2].username, 'u3')
            self.assertRaises(StopIteration, next, i)

    def test_iterator(self):
        User.create_users(10)

        with self.assertQueryCount(1):
            qr = User.select().order_by(User.id).execute()
            usernames = [u.username for u in qr.iterator()]
            self.assertEqual(usernames, ['u%d' % i for i in range(1, 11)])

        self.assertTrue(qr._populated)
        self.assertEqual(qr._result_cache, [])

        with self.assertQueryCount(0):
            again = [u.username for u in qr]
            self.assertEqual(again, [])

        with self.assertQueryCount(1):
            qr = User.select().where(User.username == 'xxx').execute()
            usernames = [u.username for u in qr.iterator()]
            self.assertEqual(usernames, [])

    def test_iterator_query_method(self):
        User.create_users(10)

        with self.assertQueryCount(1):
            qr = User.select().order_by(User.id)
            usernames = [u.username for u in qr.iterator()]
            self.assertEqual(usernames, ['u%d' % i for i in range(1, 11)])

        with self.assertQueryCount(0):
            again = [u.username for u in qr]
            self.assertEqual(again, [])

    def test_iterator_extended(self):
        User.create_users(10)
        for i in range(1, 4):
            for j in range(i):
                Blog.create(
                    title='blog-%s-%s' % (i, j),
                    user=User.get(User.username == 'u%s' % i))

        qr = (User
              .select(
                  User.username,
                  fn.Count(Blog.pk).alias('ct'))
              .join(Blog)
              .where(User.username << ['u1', 'u2', 'u3'])
              .group_by(User)
              .order_by(User.id)
              .naive())

        accum = []
        with self.assertQueryCount(1):
            for user in qr.iterator():
                accum.append((user.username, user.ct))

        self.assertEqual(accum, [
            ('u1', 1),
            ('u2', 2),
            ('u3', 3)])

        qr = (User
              .select(fn.Count(User.id).alias('ct'))
              .group_by(User.username << ['u1', 'u2', 'u3'])
              .order_by(fn.Count(User.id).desc()))
        accum = []

        with self.assertQueryCount(1):
            for ct, in qr.tuples().iterator():
                accum.append(ct)

        self.assertEqual(accum, [7, 3])

    def test_fill_cache(self):
        def assertUsernames(qr, n):
            self.assertEqual([u.username for u in qr._result_cache], ['u%d' % i for i in range(1, n+1)])

        User.create_users(20)

        with self.assertQueryCount(1):
            qr = User.select().execute()

            qr.fill_cache(5)
            self.assertFalse(qr._populated)
            assertUsernames(qr, 5)

            # a subsequent call will not "over-fill"
            qr.fill_cache(5)
            self.assertFalse(qr._populated)
            assertUsernames(qr, 5)

            # ask for one more and ye shall receive
            qr.fill_cache(6)
            self.assertFalse(qr._populated)
            assertUsernames(qr, 6)

            qr.fill_cache(21)
            self.assertTrue(qr._populated)
            assertUsernames(qr, 20)

            self.assertRaises(StopIteration, next, qr)

    def test_select_related(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')
        c11 = Comment.create(blog=b1, comment='c11')
        c12 = Comment.create(blog=b1, comment='c12')
        c21 = Comment.create(blog=b2, comment='c21')
        c22 = Comment.create(blog=b2, comment='c22')

        # missing comment.blog_id
        comments = (Comment
                    .select(Comment.id, Comment.comment, Blog.pk, Blog.title)
                    .join(Blog)
                    .where(Blog.title == 'b1')
                    .order_by(Comment.id))
        with self.assertQueryCount(1):
            self.assertEqual([c.blog.title for c in comments], ['b1', 'b1'])

        # missing blog.pk
        comments = (Comment
                    .select(Comment.id, Comment.comment, Comment.blog, Blog.title)
                    .join(Blog)
                    .where(Blog.title == 'b2')
                    .order_by(Comment.id))
        with self.assertQueryCount(1):
            self.assertEqual([c.blog.title for c in comments], ['b2', 'b2'])

        # both but going up 2 levels
        comments = (Comment
                    .select(Comment, Blog, User)
                    .join(Blog)
                    .join(User)
                    .where(User.username == 'u1')
                    .order_by(Comment.id))
        with self.assertQueryCount(1):
            self.assertEqual([c.comment for c in comments], ['c11', 'c12'])
            self.assertEqual([c.blog.title for c in comments], ['b1', 'b1'])
            self.assertEqual([c.blog.user.username for c in comments], ['u1', 'u1'])

        self.assertTrue(isinstance(comments._qr, ModelQueryResultWrapper))

        comments = (Comment
                    .select()
                    .join(Blog)
                    .join(User)
                    .where(User.username == 'u1')
                    .order_by(Comment.id))
        with self.assertQueryCount(5):
            self.assertEqual([c.blog.user.username for c in comments], ['u1', 'u1'])

        self.assertTrue(isinstance(comments._qr, NaiveQueryResultWrapper))

        # Go up two levels and use aliases for the joined instances.
        comments = (Comment
                    .select(Comment, Blog, User)
                    .join(Blog, on=(Comment.blog == Blog.pk).alias('bx'))
                    .join(User, on=(Blog.user == User.id).alias('ux'))
                    .where(User.username == 'u1')
                    .order_by(Comment.id))
        with self.assertQueryCount(1):
            self.assertEqual([c.comment for c in comments], ['c11', 'c12'])
            self.assertEqual([c.bx.title for c in comments], ['b1', 'b1'])
            self.assertEqual([c.bx.ux.username for c in comments], ['u1', 'u1'])

    def test_naive(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')

        users = User.select().naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])
        self.assertTrue(isinstance(users._qr, NaiveQueryResultWrapper))

        users = User.select(User, Blog).join(Blog).naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])
        self.assertEqual([u.title for u in users], ['b1', 'b2'])

        query = Blog.select(Blog, User).join(User).order_by(Blog.title).naive()
        self.assertEqual(query.get().user, User.get(User.username == 'u1'))

    def test_tuples_dicts(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')
        users = User.select().tuples().order_by(User.id)
        self.assertEqual([r for r in users], [
            (u1.id, 'u1'),
            (u2.id, 'u2'),
        ])

        users = User.select().dicts()
        self.assertEqual([r for r in users], [
            {'id': u1.id, 'username': 'u1'},
            {'id': u2.id, 'username': 'u2'},
        ])

        users = User.select(User, Blog).join(Blog).order_by(User.id).tuples()
        self.assertEqual([r for r in users], [
            (u1.id, 'u1', b1.pk, u1.id, 'b1', '', None),
            (u2.id, 'u2', b2.pk, u2.id, 'b2', '', None),
        ])

        users = User.select(User, Blog).join(Blog).order_by(User.id).dicts()
        self.assertEqual([r for r in users], [
            {'id': u1.id, 'username': 'u1', 'pk': b1.pk, 'user': u1.id, 'title': 'b1', 'content': '', 'pub_date': None},
            {'id': u2.id, 'username': 'u2', 'pk': b2.pk, 'user': u2.id, 'title': 'b2', 'content': '', 'pub_date': None},
        ])

        users = User.select().order_by(User.id).namedtuples()
        self.assertEqual([(r.id, r.username) for r in users],
                         [(u1.id, 'u1'), (u2.id, 'u2')])

        users = (User
                 .select(
                     User.id,
                     User.username,
                     fn.UPPER(User.username).alias('USERNAME'),
                     (User.id + 2).alias('xid'))
                 .order_by(User.id)
                 .namedtuples())
        self.assertEqual(
            [(r.id, r.username, r.USERNAME, r.xid) for r in users],
            [(u1.id, 'u1', 'U1', u1.id + 2), (u2.id, 'u2', 'U2', u2.id + 2)])

    def test_slicing_dicing(self):
        def assertUsernames(users, nums):
            self.assertEqual([u.username for u in users], ['u%d' % i for i in nums])

        User.create_users(10)

        with self.assertQueryCount(1):
            uq = User.select().order_by(User.id)
            for i in range(2):
                res = uq[0]
                self.assertEqual(res.username, 'u1')

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[1]
                self.assertEqual(res.username, 'u2')

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[-1]
                self.assertEqual(res.username, 'u10')

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[:3]
                assertUsernames(res, [1, 2, 3])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[2:5]
                assertUsernames(res, [3, 4, 5])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[5:]
                assertUsernames(res, [6, 7, 8, 9, 10])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[-3:]
                assertUsernames(res, [8, 9, 10])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[-5:-3]
                assertUsernames(res, [6, 7])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[:-3]
                assertUsernames(res, list(range(1, 8)))

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[4:-4]
                assertUsernames(res, [5, 6])

        with self.assertQueryCount(0):
            for i in range(2):
                res = uq[-6:6]
                assertUsernames(res, [5, 6])

        self.assertRaises(IndexError, uq.__getitem__, 10)

        with self.assertQueryCount(0):
            res = uq[10:]
            self.assertEqual(res, [])

        uq = uq.clone()
        with self.assertQueryCount(1):
            for _ in range(2):
                res = uq[-1]
                self.assertEqual(res.username, 'u10')

    def test_indexing_fill_cache(self):
        def assertUser(query_or_qr, idx):
            self.assertEqual(query_or_qr[idx].username, 'u%d' % (idx + 1))

        User.create_users(10)
        uq = User.select().order_by(User.id)

        with self.assertQueryCount(1):
            # Ensure we can grab the first 5 users in 1 query.
            for i in range(5):
                assertUser(uq, i)

        # Iterate in reverse and ensure only costs 1 query.
        uq = User.select().order_by(User.id)

        with self.assertQueryCount(1):
            for i in reversed(range(10)):
                assertUser(uq, i)

        # Execute the query and get reference to result wrapper.
        query = User.select().order_by(User.id)
        query.execute()
        qr = query._qr

        # Getting the first user will populate the result cache with 1 obj.
        assertUser(query, 0)
        self.assertEqual(len(qr._result_cache), 1)

        # Getting the last user will fill the cache.
        assertUser(query, 9)
        self.assertEqual(len(qr._result_cache), 10)

    def test_prepared(self):
        for i in range(2):
            u = User.create(username='u%d' % i)
            for j in range(2):
                Blog.create(title='b%d-%d' % (i, j), user=u, content='')

        for u in User.select():
            # check prepared was called
            self.assertEqual(u.foo, u.username)

        for b in Blog.select(Blog, User).join(User):
            # prepared is called for select-related instances
            self.assertEqual(b.foo, b.title)
            self.assertEqual(b.user.foo, b.user.username)

    def test_aliasing_values(self):
        User.create_users(2)
        q = User.select(User.username.alias('xx')).order_by(User.username)
        results = [row for row in q.dicts()]
        self.assertEqual(results, [
            {'xx': 'u1'},
            {'xx': 'u2'}])

        results = [user.xx for user in q]
        self.assertEqual(results, ['u1', 'u2'])

        # Force ModelQueryResultWrapper.
        q = (User
             .select(User.username.alias('xx'), Blog.pk)
             .join(Blog, JOIN.LEFT_OUTER)
             .order_by(User.username))
        results = [user.xx for user in q]
        self.assertEqual(results, ['u1', 'u2'])

        # Use Model and Field aliases.
        UA = User.alias()
        q = (User
             .select(
                 User.username.alias('x'),
                 UA.username.alias('y'))
             .join(UA, on=(User.id == UA.id).alias('z'))
             .order_by(User.username))
        results = [(user.x, user.z.y) for user in q]
        self.assertEqual(results, [('u1', 'u1'), ('u2', 'u2')])

        q = q.naive()
        results = [(user.x, user.y) for user in q]
        self.assertEqual(results, [('u1', 'u1'), ('u2', 'u2')])

        uq = User.select(User.id, User.username).alias('u2')
        q = (User
             .select(
                 User.username.alias('x'),
                 uq.c.username.alias('y'))
             .join(uq, on=(User.id == uq.c.id))
             .order_by(User.username))
        results = [(user.x, user.y) for user in q]
        self.assertEqual(results, [('u1', 'u1'), ('u2', 'u2')])


class TestJoinedInstanceConstruction(ModelTestCase):
    requires = [Blog, User, Relationship]

    def setUp(self):
        super(TestJoinedInstanceConstruction, self).setUp()
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        Blog.create(user=u1, title='b1')
        Blog.create(user=u2, title='b2')

    def test_fk_missing_pk(self):
        # Not enough information.
        with self.assertQueryCount(1):
            q = (Blog
                 .select(Blog.title, User.username)
                 .join(User)
                 .order_by(Blog.title, User.username))
            results = []
            for blog in q:
                results.append((blog.title, blog.user.username))
                self.assertIsNone(blog.user.id)
                self.assertIsNone(blog.user_id)
            self.assertEqual(results, [('b1', 'u1'), ('b2', 'u2')])

    def test_fk_with_pk(self):
        with self.assertQueryCount(1):
            q = (Blog
                 .select(Blog.title, User.username, User.id)
                 .join(User)
                 .order_by(Blog.title, User.username))
            results = []
            for blog in q:
                results.append((blog.title, blog.user.username))
                self.assertIsNotNone(blog.user.id)
                self.assertIsNotNone(blog.user_id)
            self.assertEqual(results, [('b1', 'u1'), ('b2', 'u2')])

    def test_backref_missing_pk(self):
        with self.assertQueryCount(1):
            q = (User
                 .select(User.username, Blog.title)
                 .join(Blog)
                 .order_by(User.username, Blog.title))
            results = []
            for user in q:
                results.append((user.username, user.blog.title))
                self.assertIsNone(user.id)
                self.assertIsNone(user.blog.pk)
                self.assertIsNone(user.blog.user_id)
            self.assertEqual(results, [('u1', 'b1'), ('u2', 'b2')])

    def test_fk_join_expr(self):
        with self.assertQueryCount(1):
            q = (User
                 .select(User.username, Blog.title)
                 .join(Blog, on=(User.id == Blog.user).alias('bx'))
                 .order_by(User.username))
            results = []
            for user in q:
                results.append((user.username, user.bx.title))
            self.assertEqual(results, [('u1', 'b1'), ('u2', 'b2')])

        with self.assertQueryCount(1):
            q = (Blog
                 .select(Blog.title, User.username)
                 .join(User, on=(Blog.user == User.id).alias('ux'))
                 .order_by(Blog.title))
            results = []
            for blog in q:
                results.append((blog.title, blog.ux.username))
            self.assertEqual(results, [('b1', 'u1'), ('b2', 'u2')])

    def test_aliases(self):
        B = Blog.alias()
        U = User.alias()
        with self.assertQueryCount(1):
            q = (U.select(U.username, B.title)
                 .join(B, on=(U.id == B.user))
                 .order_by(U.username))
            results = []
            for user in q:
                results.append((user.username, user.blog.title))
            self.assertEqual(results, [('u1', 'b1'), ('u2', 'b2')])

        with self.assertQueryCount(1):
            q = (B.select(B.title, U.username)
                 .join(U, on=(B.user == U.id))
                 .order_by(B.title))
            results = []
            for blog in q:
                results.append((blog.title, blog.user.username))
            self.assertEqual(results, [('b1', 'u1'), ('b2', 'u2')])

        # No explicit join condition.
        with self.assertQueryCount(1):
            q = (B.select(B.title, U.username)
                 .join(U, on=B.user)
                 .order_by(B.title))
            results = [(blog.title, blog.user.username) for blog in q]
            self.assertEqual(results, [('b1', 'u1'), ('b2', 'u2')])

        # No explicit condition, backref.
        Blog.create(user=User.get(User.username == 'u2'), title='b2-2')
        with self.assertQueryCount(1):
            q = (U.select(U.username, B.title)
                 .join(B, on=B.user)
                 .order_by(U.username, B.title))
            results = [(user.username, user.blog.title) for user in q]
            self.assertEqual(
                results,
                [('u1', 'b1'), ('u2', 'b2'), ('u2', 'b2-2')])

    def test_subqueries(self):
        uq = User.select()
        bq = Blog.select(Blog.title, Blog.user).alias('bq')
        with self.assertQueryCount(1):
            q = (User
                 .select(User, bq.c.title.bind_to(Blog))
                 .join(bq, on=(User.id == bq.c.user_id).alias('blog'))
                 .order_by(User.username))
            results = []
            for user in q:
                results.append((user.username, user.blog.title))
            self.assertEqual(results, [('u1', 'b1'), ('u2', 'b2')])

    def test_multiple_joins(self):
        Blog.delete().execute()
        User.delete().execute()
        users = [User.create(username='u%s' % i) for i in range(4)]
        for from_user, to_user in itertools.combinations(users, 2):
            Relationship.create(from_user=from_user, to_user=to_user)

        with self.assertQueryCount(1):
            ToUser = User.alias()
            q = (Relationship
                 .select(Relationship, User, ToUser)
                 .join(User, on=Relationship.from_user)
                 .switch(Relationship)
                 .join(ToUser, on=Relationship.to_user)
                 .order_by(User.username, ToUser.username))

            results = [(r.from_user.username, r.to_user.username) for r in q]

        self.assertEqual(results, [
            ('u0', 'u1'),
            ('u0', 'u2'),
            ('u0', 'u3'),
            ('u1', 'u2'),
            ('u1', 'u3'),
            ('u2', 'u3'),
        ])

        with self.assertQueryCount(1):
            ToUser = User.alias()
            q = (Relationship
                 .select(Relationship, User, ToUser)
                 .join(User,
                       on=(Relationship.from_user == User.id))
                 .switch(Relationship)
                 .join(ToUser,
                       on=(Relationship.to_user == ToUser.id).alias('to_user'))
                 .order_by(User.username, ToUser.username))

            results = [(r.from_user.username, r.to_user.username) for r in q]

        self.assertEqual(results, [
            ('u0', 'u1'),
            ('u0', 'u2'),
            ('u0', 'u3'),
            ('u1', 'u2'),
            ('u1', 'u3'),
            ('u2', 'u3'),
        ])


class TestQueryResultTypeConversion(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestQueryResultTypeConversion, self).setUp()
        for i in range(3):
            User.create(username='u%d' % i)

    def assertNames(self, query, expected, attr='username'):
        id_field = query.model_class.id
        self.assertEqual(
            [getattr(item, attr) for item in query.order_by(id_field)],
            expected)

    def test_simple_select(self):
        query = UpperUser.select()
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = User.select()
        self.assertNames(query, ['u0', 'u1', 'u2'])

    def test_with_alias(self):
        # Even when aliased to a different attr, the column is coerced.
        query = UpperUser.select(UpperUser.username.alias('foo'))
        self.assertNames(query, ['U0', 'U1', 'U2'], 'foo')

    def test_scalar(self):
        max_username = (UpperUser
                        .select(fn.Max(UpperUser.username))
                        .scalar(convert=True))
        self.assertEqual(max_username, 'U2')

        max_username = (UpperUser
                        .select(fn.Max(UpperUser.username))
                        .scalar())
        self.assertEqual(max_username, 'u2')

    def test_function(self):
        substr = fn.SubStr(UpperUser.username, 1, 3)

        # Being the first parameter of the function, it meets the special-case
        # criteria.
        query = UpperUser.select(substr.alias('foo'))
        self.assertNames(query, ['U0', 'U1', 'U2'], 'foo')

        query = UpperUser.select(substr.coerce(False).alias('foo'))
        self.assertNames(query, ['u0', 'u1', 'u2'], 'foo')

        query = UpperUser.select(substr.coerce(False).alias('username'))
        self.assertNames(query, ['u0', 'u1', 'u2'])

        query = UpperUser.select(fn.Lower(UpperUser.username).alias('username'))
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = UpperUser.select(
            fn.Lower(UpperUser.username).alias('username').coerce(False))
        self.assertNames(query, ['u0', 'u1', 'u2'])

        # Since it is aliased to an existing column, we will use that column's
        # coerce.
        query = UpperUser.select(
            fn.SubStr(fn.Lower(UpperUser.username), 1, 3).alias('username'))
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = UpperUser.select(
            fn.SubStr(fn.Lower(UpperUser.username), 1, 3).alias('foo'))
        self.assertNames(query, ['u0', 'u1', 'u2'], 'foo')

class TestModelQueryResultWrapper(ModelTestCase):
    requires = [TestModelA, TestModelB, TestModelC, User, Blog]

    data = (
        (TestModelA, (
            ('pk1', 'a1'),
            ('pk2', 'a2'),
            ('pk3', 'a3'))),
        (TestModelB, (
            ('pk1', 'b1'),
            ('pk2', 'b2'),
            ('pk3', 'b3'))),
        (TestModelC, (
            ('pk1', 'c1'),
            ('pk2', 'c2'))),
    )

    def setUp(self):
        super(TestModelQueryResultWrapper, self).setUp()
        for model_class, model_data in self.data:
            for pk, data in model_data:
                model_class.create(field=pk, data=data)

    def test_join_expr(self):
        def get_query(join_type=JOIN.INNER):
            sq = (TestModelA
                  .select(TestModelA, TestModelB, TestModelC)
                  .join(
                      TestModelB,
                      on=(TestModelA.field == TestModelB.field).alias('rel_b'))
                  .join(
                      TestModelC,
                      join_type=join_type,
                      on=(TestModelB.field == TestModelC.field))
                  .order_by(TestModelA.field))
            return sq

        sq = get_query()
        self.assertEqual(sq.count(), 2)

        with self.assertQueryCount(1):
            results = list(sq)
            expected = (('b1', 'c1'), ('b2', 'c2'))
            for i, (b_data, c_data) in enumerate(expected):
                self.assertEqual(results[i].rel_b.data, b_data)
                self.assertEqual(results[i].rel_b.field.data, c_data)

        sq = get_query(JOIN.LEFT_OUTER)
        self.assertEqual(sq.count(), 3)

        with self.assertQueryCount(1):
            results = list(sq)
            expected = (('b1', 'c1'), ('b2', 'c2'), ('b3', None))
            for i, (b_data, c_data) in enumerate(expected):
                self.assertEqual(results[i].rel_b.data, b_data)
                self.assertEqual(results[i].rel_b.field.data, c_data)

    def test_backward_join(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        for user in (u1, u2):
            Blog.create(title='b-%s' % user.username, user=user)

        # Create an additional blog for user 2.
        Blog.create(title='b-u2-2', user=u2)

        res = (User
               .select(User.username, Blog.title)
               .join(Blog)
               .order_by(User.username.asc(), Blog.title.asc()))
        self.assertEqual([(u.username, u.blog.title) for u in res], [
            ('u1', 'b-u1'),
            ('u2', 'b-u2'),
            ('u2', 'b-u2-2')])

    def test_joins_with_aliases(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1_1 = Blog.create(user=u1, title='b1-1')
        b1_2 = Blog.create(user=u1, title='b1-2')
        b2_1 = Blog.create(user=u2, title='b2-1')

        UserAlias = User.alias()
        BlogAlias = Blog.alias()

        def assertExpectedQuery(query, is_user_query):
            accum = []

            with self.assertQueryCount(1):
                if is_user_query:
                    for user in query:
                        accum.append((user.username, user.blog.title))
                else:
                    for blog in query:
                        accum.append((blog.user.username, blog.title))

            self.assertEqual(accum, [
                ('u1', 'b1-1'),
                ('u1', 'b1-2'),
                ('u2', 'b2-1'),
            ])

        combinations = [
            (User, BlogAlias, User.id == BlogAlias.user, True),
            (User, BlogAlias, BlogAlias.user == User.id, True),
            (User, Blog, User.id == Blog.user, True),
            (User, Blog, Blog.user == User.id, True),
            (User, Blog, None, True),
            (Blog, UserAlias, UserAlias.id == Blog.user, False),
            (Blog, UserAlias, Blog.user == UserAlias.id, False),
            (Blog, User, User.id == Blog.user, False),
            (Blog, User, Blog.user == User.id, False),
            (Blog, User, None, False),
        ]
        for Src, JoinModel, predicate, is_user_query in combinations:
            query = (Src
                     .select(Src, JoinModel)
                     .join(JoinModel, on=predicate)
                     .order_by(SQL('1, 2')))
            assertExpectedQuery(query, is_user_query)

class TestModelQueryResultForeignKeys(ModelTestCase):
    requires = [Parent, Child]

    def test_foreign_key_assignment(self):
        parent = Parent.create(data='p1')
        child = Child.create(parent=parent, data='c1')
        ParentAlias = Parent.alias()

        query = Child.select(Child, ParentAlias)

        ljoin = (ParentAlias.id == Child.parent)
        rjoin = (Child.parent == ParentAlias.id)

        lhs_alias = query.join(ParentAlias, on=ljoin)
        rhs_alias = query.join(ParentAlias, on=rjoin)

        self.assertJoins(lhs_alias, [
            'INNER JOIN "parent" AS parent '
            'ON ("parent"."id" = "child"."parent_id")'])

        self.assertJoins(rhs_alias, [
            'INNER JOIN "parent" AS parent '
            'ON ("child"."parent_id" = "parent"."id")'])

        with self.assertQueryCount(1):
            lchild = lhs_alias.get()
            self.assertEqual(lchild.id, child.id)
            self.assertEqual(lchild.parent.id, parent.id)

        with self.assertQueryCount(1):
            rchild = rhs_alias.get()
            self.assertEqual(rchild.id, child.id)
            self.assertEqual(rchild.parent.id, parent.id)

class TestSelectRelatedForeignKeyToNonPrimaryKey(ModelTestCase):
    requires = [Package, PackageItem]

    def test_select_related(self):
        p1 = Package.create(barcode='101')
        p2 = Package.create(barcode='102')
        pi11 = PackageItem.create(title='p11', package='101')
        pi12 = PackageItem.create(title='p12', package='101')
        pi21 = PackageItem.create(title='p21', package='102')
        pi22 = PackageItem.create(title='p22', package='102')

        # missing PackageItem.package_id.
        with self.assertQueryCount(1):
            items = (PackageItem
                     .select(
                         PackageItem.id, PackageItem.title, Package.barcode)
                     .join(Package)
                     .where(Package.barcode == '101')
                     .order_by(PackageItem.id))
            self.assertEqual(
                [i.package.barcode for i in items],
                ['101', '101'])

        with self.assertQueryCount(1):
            items = (PackageItem
                     .select(
                         PackageItem.id, PackageItem.title, PackageItem.package, Package.id)
                     .join(Package)
                     .where(Package.barcode == '101')
                     .order_by(PackageItem.id))
            self.assertEqual([i.package.id for i in items], [p1.id, p1.id])


class BaseTestPrefetch(ModelTestCase):
    requires = [
        User,
        Blog,
        Comment,
        Parent,
        Child,
        Orphan,
        ChildPet,
        OrphanPet,
        Category,
        Post,
        Tag,
        TagPostThrough,
        TagPostThroughAlt,
        Category,
        UserCategory,
        Relationship,
        SpecialComment,
    ]

    user_data = [
        ('u1', (('b1', ('b1-c1', 'b1-c2')), ('b2', ('b2-c1',)))),
        ('u2', ()),
        ('u3', (('b3', ('b3-c1', 'b3-c2')), ('b4', ()))),
        ('u4', (('b5', ('b5-c1', 'b5-c2')), ('b6', ('b6-c1',)))),
    ]
    parent_data = [
        ('p1', (
            # children
            (
                ('c1', ('c1-p1', 'c1-p2')),
                ('c2', ('c2-p1',)),
                ('c3', ('c3-p1',)),
                ('c4', ()),
            ),
            # orphans
            (
                ('o1', ('o1-p1', 'o1-p2')),
                ('o2', ('o2-p1',)),
                ('o3', ('o3-p1',)),
                ('o4', ()),
            ),
        )),
        ('p2', ((), ())),
        ('p3', (
            # children
            (
                ('c6', ()),
                ('c7', ('c7-p1',)),
            ),
            # orphans
            (
                ('o6', ('o6-p1', 'o6-p2')),
                ('o7', ('o7-p1',)),
            ),
        )),
    ]

    category_tree = [
        ['root', ['p1', 'p2']],
        ['p1', ['p1-1', 'p1-2']],
        ['p2', ['p2-1', 'p2-2']],
        ['p1-1', []],
        ['p1-2', []],
        ['p2-1', []],
        ['p2-2', []],
    ]

    def setUp(self):
        super(BaseTestPrefetch, self).setUp()
        for parent, (children, orphans) in self.parent_data:
            p = Parent.create(data=parent)
            for child_pets in children:
                child, pets = child_pets
                c = Child.create(parent=p, data=child)
                for pet in pets:
                    ChildPet.create(child=c, data=pet)
            for orphan_pets in orphans:
                orphan, pets = orphan_pets
                o = Orphan.create(parent=p, data=orphan)
                for pet in pets:
                    OrphanPet.create(orphan=o, data=pet)

        for user, blog_comments in self.user_data:
            u = User.create(username=user)
            for blog, comments in blog_comments:
                b = Blog.create(user=u, title=blog, content='')
                for c in comments:
                    Comment.create(blog=b, comment=c)

    def _build_category_tree(self):
        def cc(name, parent=None):
            return Category.create(name=name, parent=parent)
        root = cc('root')
        p1 = cc('p1', root)
        p2 = cc('p2', root)
        for p in (p1, p2):
            for i in range(2):
                cc('%s-%s' % (p.name, i + 1), p)


class TestPrefetch(BaseTestPrefetch):
    def test_prefetch_simple(self):
        sq = User.select().where(User.username != 'u3')
        sq2 = Blog.select().where(Blog.title != 'b2')
        sq3 = Comment.select()

        with self.assertQueryCount(3):
            prefetch_sq = prefetch(sq, sq2, sq3)
            results = []
            for user in prefetch_sq:
                results.append(user.username)
                for blog in user.blog_set_prefetch:
                    results.append(blog.title)
                    for comment in blog.comments_prefetch:
                        results.append(comment.comment)

            self.assertEqual(results, [
                'u1', 'b1', 'b1-c1', 'b1-c2',
                'u2',
                'u4', 'b5', 'b5-c1', 'b5-c2', 'b6', 'b6-c1',
            ])

        with self.assertQueryCount(0):
            results = []
            for user in prefetch_sq:
                for blog in user.blog_set_prefetch:
                    results.append(blog.user.username)
                    for comment in blog.comments_prefetch:
                        results.append(comment.blog.title)
            self.assertEqual(results, [
                'u1', 'b1', 'b1', 'u4', 'b5', 'b5', 'u4', 'b6',
            ])

    def test_prefetch_reverse(self):
        sq = User.select()
        sq2 = Blog.select().where(Blog.title != 'b2').order_by(Blog.pk)

        with self.assertQueryCount(2):
            prefetch_sq = prefetch(sq2, sq)
            results = []
            for blog in prefetch_sq:
                results.append(blog.title)
                results.append(blog.user.username)

        self.assertEqual(results, [
            'b1', 'u1',
            'b3', 'u3',
            'b4', 'u3',
            'b5', 'u4',
            'b6', 'u4'])

    def test_prefetch_up_and_down(self):
        blogs = Blog.select(Blog, User).join(User).order_by(Blog.title)
        comments = Comment.select().order_by(Comment.comment.desc())

        with self.assertQueryCount(2):
            query = prefetch(blogs, comments)
            results = []
            for blog in query:
                results.append((
                    blog.user.username,
                    blog.title,
                    [comment.comment for comment in blog.comments_prefetch]))

            self.assertEqual(results, [
                ('u1', 'b1', ['b1-c2', 'b1-c1']),
                ('u1', 'b2', ['b2-c1']),
                ('u3', 'b3', ['b3-c2', 'b3-c1']),
                ('u3', 'b4', []),
                ('u4', 'b5', ['b5-c2', 'b5-c1']),
                ('u4', 'b6', ['b6-c1']),
            ])

    def test_prefetch_multi_depth(self):
        sq = Parent.select()
        sq2 = Child.select()
        sq3 = Orphan.select()
        sq4 = ChildPet.select()
        sq5 = OrphanPet.select()

        with self.assertQueryCount(5):
            prefetch_sq = prefetch(sq, sq2, sq3, sq4, sq5)
            results = []
            for parent in prefetch_sq:
                results.append(parent.data)
                for child in parent.child_set_prefetch:
                    results.append(child.data)
                    for pet in child.childpet_set_prefetch:
                        results.append(pet.data)

                for orphan in parent.orphan_set_prefetch:
                    results.append(orphan.data)
                    for pet in orphan.orphanpet_set_prefetch:
                        results.append(pet.data)

            self.assertEqual(results, [
                'p1', 'c1', 'c1-p1', 'c1-p2', 'c2', 'c2-p1', 'c3', 'c3-p1', 'c4',
                      'o1', 'o1-p1', 'o1-p2', 'o2', 'o2-p1', 'o3', 'o3-p1', 'o4',
                'p2',
                'p3', 'c6', 'c7', 'c7-p1', 'o6', 'o6-p1', 'o6-p2', 'o7', 'o7-p1',
            ])

    def test_prefetch_no_aggregate(self):
        with self.assertQueryCount(1):
            query = (User
                     .select(User, Blog)
                     .join(Blog, JOIN.LEFT_OUTER)
                     .order_by(User.username, Blog.title))
            results = []
            for user in query:
                results.append((
                    user.username,
                    user.blog.title))

            self.assertEqual(results, [
                ('u1', 'b1'),
                ('u1', 'b2'),
                ('u2', None),
                ('u3', 'b3'),
                ('u3', 'b4'),
                ('u4', 'b5'),
                ('u4', 'b6'),
            ])

    def test_prefetch_group_by(self):
        users = (User
                 .select(User, fn.Max(fn.Length(Blog.content)).alias('max_content_len'))
                 .join(Blog, JOIN_LEFT_OUTER)
                 .group_by(User)
                 .order_by(User.id))
        blogs = Blog.select()
        comments = Comment.select()
        with self.assertQueryCount(3):
            result = prefetch(users, blogs, comments)
            self.assertEqual(len(result), 4)


    def test_prefetch_self_join(self):
        self._build_category_tree()
        Child = Category.alias()
        with self.assertQueryCount(2):
            query = prefetch(Category.select().order_by(Category.id), Child)
            names_and_children = [
                [parent.name, [child.name for child in parent.children_prefetch]]
                for parent in query]

        self.assertEqual(names_and_children, self.category_tree)

    def test_prefetch_specific_model(self):
        # User -> Blog
        #      -> SpecialComment (fk to user and blog)
        Comment.delete().execute()
        Blog.delete().execute()
        User.delete().execute()
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        for i in range(1, 3):
            for user in (u1, u2):
                b = Blog.create(user=user, title='%s-b%s' % (user.username, i))
                SpecialComment.create(
                    user=user,
                    blog=b,
                    name='%s-c%s' % (user.username, i))

        u3 = User.create(username='u3')
        SpecialComment.create(user=u3, name='u3-c1')

        u4 = User.create(username='u4')
        Blog.create(user=u4, title='u4-b1')

        u5 = User.create(username='u5')

        with self.assertQueryCount(3):
            user_pf = prefetch(
                User.select(),
                Blog,
                (SpecialComment, User))
            results = []
            for user in user_pf:
                results.append((
                    user.username,
                    [b.title for b in user.blog_set_prefetch],
                    [c.name for c in user.special_comments_prefetch]))

        self.assertEqual(results, [
            ('u1', ['u1-b1', 'u1-b2'], ['u1-c1', 'u1-c2']),
            ('u2', ['u2-b1', 'u2-b2'], ['u2-c1', 'u2-c2']),
            ('u3', [], ['u3-c1']),
            ('u4', ['u4-b1'], []),
            ('u5', [], []),
        ])


class TestPrefetchMultipleFKs(ModelTestCase):
    requires = [
        User,
        Blog,
        Relationship,
    ]

    def create_users(self):
        names = ['charlie', 'huey', 'zaizee']
        return [User.create(username=username) for username in names]

    def create_relationships(self, charlie, huey, zaizee):
        r1 = Relationship.create(from_user=charlie, to_user=huey)
        r2 = Relationship.create(from_user=charlie, to_user=zaizee)
        r3 = Relationship.create(from_user=huey, to_user=charlie)
        r4 = Relationship.create(from_user=zaizee, to_user=charlie)
        return r1, r2, r3, r4

    def test_multiple_fks(self):
        charlie, huey, zaizee = self.create_users()
        r1, r2, r3, r4 = self.create_relationships(charlie, huey, zaizee)

        def assertRelationships(attr, values):
            for relationship, value in zip(attr, values):
                self.assertEqual(relationship._data, value)

        with self.assertQueryCount(2):
            users = User.select().order_by(User.id)
            relationships = Relationship.select()

            query = prefetch(users, relationships)
            results = [row for row in query]
            self.assertEqual(len(results), 3)

            cp, hp, zp = results

            assertRelationships(cp.relationships_prefetch, [
                {'id': r1.id, 'from_user': charlie.id, 'to_user': huey.id},
                {'id': r2.id, 'from_user': charlie.id, 'to_user': zaizee.id}])
            assertRelationships(cp.related_to_prefetch, [
                {'id': r3.id, 'from_user': huey.id, 'to_user': charlie.id},
                {'id': r4.id, 'from_user': zaizee.id, 'to_user': charlie.id}])

            assertRelationships(hp.relationships_prefetch, [
                {'id': r3.id, 'from_user': huey.id, 'to_user': charlie.id}])
            assertRelationships(hp.related_to_prefetch, [
                {'id': r1.id, 'from_user': charlie.id, 'to_user': huey.id}])

            assertRelationships(zp.relationships_prefetch, [
                {'id': r4.id, 'from_user': zaizee.id, 'to_user': charlie.id}])
            assertRelationships(zp.related_to_prefetch, [
                {'id': r2.id, 'from_user': charlie.id, 'to_user': zaizee.id}])

    def test_prefetch_multiple_fk_reverse(self):
        charlie, huey, zaizee = self.create_users()
        r1, r2, r3, r4 = self.create_relationships(charlie, huey, zaizee)

        with self.assertQueryCount(2):
            relationships = Relationship.select().order_by(Relationship.id)
            users = User.select()

            query = prefetch(relationships, users)
            results = [row for row in query]
            self.assertEqual(len(results), 4)

            expected = (
                ('charlie', 'huey'),
                ('charlie', 'zaizee'),
                ('huey', 'charlie'),
                ('zaizee', 'charlie'))
            for (from_user, to_user), relationship in zip(expected, results):
                self.assertEqual(relationship.from_user.username, from_user)
                self.assertEqual(relationship.to_user.username, to_user)


class TestPrefetchThroughM2M(ModelTestCase):
    requires = [User, Note, Flag, NoteFlag]
    test_data = [
        ('charlie', [
            ('rewrite peewee', ['todo']),
            ('rice desktop', ['done']),
            ('test peewee', ['todo', 'urgent']),
            ('write window-manager', [])]),
        ('huey', [
            ('bite mickey', []),
            ('scratch furniture', ['todo', 'urgent']),
            ('vomit on carpet', ['done'])]),
        ('zaizee', []),
    ]

    def setUp(self):
        super(TestPrefetchThroughM2M, self).setUp()
        with test_db.atomic():
            for username, note_data in self.test_data:
                user = User.create(username=username)
                for note, flags in note_data:
                    self.create_note(user, note, *flags)

    def create_note(self, user, text, *flags):
        note = Note.create(user=user, text=text)
        for flag in flags:
            try:
                flag = Flag.get(Flag.label == flag)
            except Flag.DoesNotExist:
                flag = Flag.create(label=flag)
            NoteFlag.create(note=note, flag=flag)
        return note

    def test_prefetch_through_m2m(self):
        # One query for each table being prefetched.
        with self.assertQueryCount(4):
            users = User.select()
            notes = Note.select().order_by(Note.text)
            flags = Flag.select().order_by(Flag.label)
            query = prefetch(users, notes, NoteFlag, flags)
            accum = []
            for user in query:
                notes = []
                for note in user.notes_prefetch:
                    flags = []
                    for nf in note.flags_prefetch:
                        self.assertEqual(nf.note_id, note.id)
                        self.assertEqual(nf.note.id, note.id)
                        flags.append(nf.flag.label)
                    notes.append((note.text, flags))
                accum.append((user.username, notes))

        self.assertEqual(self.test_data, accum)

    def test_aggregate_through_m2m(self):
        with self.assertQueryCount(1):
            query = (User
                     .select(User, Note, NoteFlag, Flag)
                     .join(Note, JOIN.LEFT_OUTER)
                     .join(NoteFlag, JOIN.LEFT_OUTER)
                     .join(Flag, JOIN.LEFT_OUTER)
                     .order_by(User.id, Note.text, Flag.label)
                     .aggregate_rows())

            accum = []
            for user in query:
                notes = []
                for note in user.notes:
                    flags = []
                    for nf in note.flags:
                        self.assertEqual(nf.note_id, note.id)
                        flags.append(nf.flag.label)
                    notes.append((note.text, flags))
                accum.append((user.username, notes))

        self.assertEqual(self.test_data, accum)


class TestAggregateRows(BaseTestPrefetch):
    def test_aggregate_users(self):
        with self.assertQueryCount(1):
            query = (User
                     .select(User, Blog, Comment)
                     .join(Blog, JOIN.LEFT_OUTER)
                     .join(Comment, JOIN.LEFT_OUTER)
                     .order_by(User.username, Blog.title, Comment.id)
                     .aggregate_rows())

            results = []
            for user in query:
                results.append((
                    user.username,
                    [(blog.title,
                      [comment.comment for comment in blog.comments])
                     for blog in user.blog_set]))

        self.assertEqual(results, [
            ('u1', [
                ('b1', ['b1-c1', 'b1-c2']),
                ('b2', ['b2-c1'])]),
            ('u2', []),
            ('u3', [
                ('b3', ['b3-c1', 'b3-c2']),
                ('b4', [])]),
            ('u4', [
                ('b5', ['b5-c1', 'b5-c2']),
                ('b6', ['b6-c1'])]),
        ])

    def test_aggregate_blogs(self):
        with self.assertQueryCount(1):
            query = (Blog
                     .select(Blog, User, Comment)
                     .join(User)
                     .switch(Blog)
                     .join(Comment, JOIN.LEFT_OUTER)
                     .order_by(Blog.title, User.username, Comment.id)
                     .aggregate_rows())

            results = []
            for blog in query:
                results.append((
                    blog.user.username,
                    blog.title,
                    [comment.comment for comment in blog.comments]))

        self.assertEqual(results, [
            ('u1', 'b1', ['b1-c1', 'b1-c2']),
            ('u1', 'b2', ['b2-c1']),
            ('u3', 'b3', ['b3-c1', 'b3-c2']),
            ('u3', 'b4', []),
            ('u4', 'b5', ['b5-c1', 'b5-c2']),
            ('u4', 'b6', ['b6-c1']),
        ])

    def test_aggregate_on_expression_join(self):
        with self.assertQueryCount(1):
            join_expr = (User.id == Blog.user)
            query = (User
                     .select(User, Blog)
                     .join(Blog, JOIN.LEFT_OUTER, on=join_expr)
                     .order_by(User.username, Blog.title)
                     .aggregate_rows())
            results = []
            for user in query:
                results.append((
                    user.username,
                    [blog.title for blog in user.blog_set]))

        self.assertEqual(results, [
            ('u1', ['b1', 'b2']),
            ('u2', []),
            ('u3', ['b3', 'b4']),
            ('u4', ['b5', 'b6']),
        ])

    def test_aggregate_with_join_model_aliases(self):
        expected = [
            ('u1', ['b1', 'b2']),
            ('u2', []),
            ('u3', ['b3', 'b4']),
            ('u4', ['b5', 'b6']),
        ]

        with self.assertQueryCount(1):
            query = (User
                     .select(User, Blog)
                     .join(
                         Blog,
                         JOIN.LEFT_OUTER,
                         on=(User.id == Blog.user).alias('blogz'))
                     .order_by(User.id, Blog.title)
                     .aggregate_rows())
            results = [
                (user.username, [blog.title for blog in user.blogz])
                for user in query]
            self.assertEqual(results, expected)

        BlogAlias = Blog.alias()
        with self.assertQueryCount(1):
            query = (User
                     .select(User, BlogAlias)
                     .join(
                         BlogAlias,
                         JOIN.LEFT_OUTER,
                         on=(User.id == BlogAlias.user).alias('blogz'))
                     .order_by(User.id, BlogAlias.title)
                     .aggregate_rows())
            results = [
                (user.username, [blog.title for blog in user.blogz])
                for user in query]
            self.assertEqual(results, expected)

    def test_aggregate_unselected_join_backref(self):
        cat_1 = Category.create(name='category 1')
        cat_2 = Category.create(name='category 2')
        with test_db.transaction():
            for i, user in enumerate(User.select().order_by(User.username)):
                if i % 2 == 0:
                    category = cat_2
                else:
                    category = cat_1
                UserCategory.create(user=user, category=category)

        with self.assertQueryCount(1):
            # The join on UserCategory is a backref join (since the FK is on
            # UserCategory). Additionally, UserCategory/Category are not
            # selected and are only used for filtering the result set.
            query = (User
                     .select(User, Blog)
                     .join(Blog, JOIN.LEFT_OUTER)
                     .switch(User)
                     .join(UserCategory)
                     .join(Category)
                     .where(Category.name == cat_1.name)
                     .order_by(User.username, Blog.title)
                     .aggregate_rows())

            results = []
            for user in query:
                results.append((
                    user.username,
                    [blog.title for blog in user.blog_set]))

        self.assertEqual(results, [
            ('u2', []),
            ('u4', ['b5', 'b6']),
        ])

    def test_aggregate_manytomany(self):
        p1 = Post.create(title='p1')
        p2 = Post.create(title='p2')
        Post.create(title='p3')
        p4 = Post.create(title='p4')
        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')
        t3 = Tag.create(tag='t3')
        TagPostThroughAlt.create(tag=t1, post=p1)
        TagPostThroughAlt.create(tag=t2, post=p1)
        TagPostThroughAlt.create(tag=t2, post=p2)
        TagPostThroughAlt.create(tag=t3, post=p2)
        TagPostThroughAlt.create(tag=t1, post=p4)
        TagPostThroughAlt.create(tag=t2, post=p4)
        TagPostThroughAlt.create(tag=t3, post=p4)

        with self.assertQueryCount(1):
            query = (Post
                     .select(Post, TagPostThroughAlt, Tag)
                     .join(TagPostThroughAlt, JOIN.LEFT_OUTER)
                     .join(Tag, JOIN.LEFT_OUTER)
                     .order_by(Post.id, TagPostThroughAlt.post, Tag.id)
                     .aggregate_rows())
            results = []
            for post in query:
                post_data = [post.title]
                for tpt in post.tags_alt:
                    post_data.append(tpt.tag.tag)
                results.append(post_data)

        self.assertEqual(results, [
            ['p1', 't1', 't2'],
            ['p2', 't2', 't3'],
            ['p3'],
            ['p4', 't1', 't2', 't3'],
        ])

    def test_aggregate_parent_child(self):
        with self.assertQueryCount(1):
            query = (Parent
                     .select(Parent, Child, Orphan, ChildPet, OrphanPet)
                     .join(Child, JOIN.LEFT_OUTER)
                     .join(ChildPet, JOIN.LEFT_OUTER)
                     .switch(Parent)
                     .join(Orphan, JOIN.LEFT_OUTER)
                     .join(OrphanPet, JOIN.LEFT_OUTER)
                     .order_by(
                         Parent.data,
                         Child.data,
                         ChildPet.id,
                         Orphan.data,
                         OrphanPet.id)
                     .aggregate_rows())

            results = []
            for parent in query:
                results.append((
                    parent.data,
                    [(child.data, [pet.data for pet in child.childpet_set])
                     for child in parent.child_set],
                    [(orphan.data, [pet.data for pet in orphan.orphanpet_set])
                     for orphan in parent.orphan_set]
                ))

        # Without the `.aggregate_rows()` call, this would be 289!!
        self.assertEqual(results, [
            ('p1',
             [('c1', ['c1-p1', 'c1-p2']),
              ('c2', ['c2-p1']),
              ('c3', ['c3-p1']),
              ('c4', [])],
             [('o1', ['o1-p1', 'o1-p2']),
              ('o2', ['o2-p1']),
              ('o3', ['o3-p1']),
              ('o4', [])],
            ),
            ('p2', [], []),
            ('p3',
             [('c6', []),
              ('c7', ['c7-p1'])],
             [('o6', ['o6-p1', 'o6-p2']),
              ('o7', ['o7-p1'])],)
        ])

    def test_aggregate_with_unselected_joins(self):
        with self.assertQueryCount(1):
            query = (Child
                     .select(Child, ChildPet, Parent)
                     .join(ChildPet, JOIN.LEFT_OUTER)
                     .switch(Child)
                     .join(Parent)
                     .join(Orphan)
                     .join(OrphanPet)
                     .where(OrphanPet.data == 'o6-p2')
                     .order_by(Child.data, ChildPet.data)
                     .aggregate_rows())
            results = []
            for child in query:
                results.append((
                    child.data,
                    child.parent.data,
                    [child_pet.data for child_pet in child.childpet_set]))

        self.assertEqual(results, [
            ('c6', 'p3', []),
            ('c7', 'p3', ['c7-p1']),
        ])

        with self.assertQueryCount(1):
            query = (Parent
                     .select(Parent, Child, ChildPet)
                     .join(Child, JOIN.LEFT_OUTER)
                     .join(ChildPet, JOIN.LEFT_OUTER)
                     .switch(Parent)
                     .join(Orphan)
                     .join(OrphanPet)
                     .where(OrphanPet.data == 'o6-p2')
                     .order_by(Parent.data, Child.data, ChildPet.data)
                     .aggregate_rows())
            results = []
            for parent in query:
                results.append((
                    parent.data,
                    [(child.data, [pet.data for pet in child.childpet_set])
                     for child in parent.child_set]))

        self.assertEqual(results, [('p3', [
            ('c6', []),
            ('c7', ['c7-p1']),
        ])])

    def test_aggregate_rows_ordering(self):
        # Refs github #519.
        with self.assertQueryCount(1):
            query = (User
                     .select(User, Blog)
                     .join(Blog, JOIN.LEFT_OUTER)
                     .order_by(User.username.desc(), Blog.title.desc())
                     .aggregate_rows())

            accum = []
            for user in query:
                accum.append((
                    user.username,
                    [blog.title for blog in user.blog_set]))

        if sys.version_info[:2] > (2, 6):
            self.assertEqual(accum, [
                ('u4', ['b6', 'b5']),
                ('u3', ['b4', 'b3']),
                ('u2', []),
                ('u1', ['b2', 'b1']),
            ])

    def test_aggregate_rows_self_join(self):
        self._build_category_tree()
        Child = Category.alias()

        # Same query, but this time use an `alias` on the join expr.
        with self.assertQueryCount(1):
            query = (Category
                     .select(Category, Child)
                     .join(
                         Child,
                         JOIN.LEFT_OUTER,
                         on=(Category.id == Child.parent).alias('childrenx'))
                     .order_by(Category.id, Child.id)
                     .aggregate_rows())
            names_and_children = [
                [parent.name, [child.name for child in parent.childrenx]]
                for parent in query]

        self.assertEqual(names_and_children, self.category_tree)

    def test_multiple_fks(self):
        names = ['charlie', 'huey', 'zaizee']
        charlie, huey, zaizee = [
            User.create(username=username) for username in names]
        Relationship.create(from_user=charlie, to_user=huey)
        Relationship.create(from_user=charlie, to_user=zaizee)
        Relationship.create(from_user=huey, to_user=charlie)
        Relationship.create(from_user=zaizee, to_user=charlie)
        UserAlias = User.alias()

        with self.assertQueryCount(1):
            query = (User
                     .select(User, Relationship, UserAlias)
                     .join(
                         Relationship,
                         JOIN.LEFT_OUTER,
                         on=Relationship.from_user)
                     .join(
                         UserAlias,
                         on=(
                             Relationship.to_user == UserAlias.id
                         ).alias('to_user'))
                     .order_by(User.username, Relationship.id)
                     .where(User.username == 'charlie')
                     .aggregate_rows())

            results = [row for row in query]
            self.assertEqual(len(results), 1)

            user = results[0]
            self.assertEqual(user.username, 'charlie')
            self.assertEqual(len(user.relationships), 2)

            rh, rz = user.relationships
            self.assertEqual(rh.to_user.username, 'huey')
            self.assertEqual(rz.to_user.username, 'zaizee')

        FromUser = User.alias()
        ToUser = User.alias()
        from_join = (Relationship.from_user == FromUser.id)
        to_join = (Relationship.to_user == ToUser.id)

        with self.assertQueryCount(1):
            query = (Relationship
                     .select(Relationship, FromUser, ToUser)
                     .join(FromUser, on=from_join.alias('from_user'))
                     .switch(Relationship)
                     .join(ToUser, on=to_join.alias('to_user'))
                     .order_by(Relationship.id)
                     .aggregate_rows())
            results = [
                (relationship.from_user.username,
                 relationship.to_user.username)
                for relationship in query]
            self.assertEqual(results, [
                ('charlie', 'huey'),
                ('charlie', 'zaizee'),
                ('huey', 'charlie'),
                ('zaizee', 'charlie'),
            ])

    def test_multiple_fks_multi_depth(self):
        names = ['charlie', 'huey', 'zaizee']
        charlie, huey, zaizee = [
            User.create(username=username) for username in names]
        Relationship.create(from_user=charlie, to_user=huey)
        Relationship.create(from_user=charlie, to_user=zaizee)
        Relationship.create(from_user=huey, to_user=charlie)
        Relationship.create(from_user=zaizee, to_user=charlie)
        human = Category.create(name='human')
        kitty = Category.create(name='kitty')
        UserCategory.create(user=charlie, category=human)
        UserCategory.create(user=huey, category=kitty)
        UserCategory.create(user=zaizee, category=kitty)

        FromUser = User.alias()
        ToUser = User.alias()
        from_join = (Relationship.from_user == FromUser.id)
        to_join = (Relationship.to_user == ToUser.id)

        FromUserCategory = UserCategory.alias()
        ToUserCategory = UserCategory.alias()
        from_uc_join = (FromUser.id == FromUserCategory.user)
        to_uc_join = (ToUser.id == ToUserCategory.user)

        FromCategory = Category.alias()
        ToCategory = Category.alias()
        from_c_join = (FromUserCategory.category == FromCategory.id)
        to_c_join = (ToUserCategory.category == ToCategory.id)

        with self.assertQueryCount(1):
            query = (Relationship
                     .select(
                         Relationship,
                         FromUser,
                         ToUser,
                         FromUserCategory,
                         ToUserCategory,
                         FromCategory,
                         ToCategory)
                     .join(FromUser, on=from_join.alias('from_user'))
                     .join(FromUserCategory, on=from_uc_join.alias('fuc'))
                     .join(FromCategory, on=from_c_join.alias('category'))
                     .switch(Relationship)
                     .join(ToUser, on=to_join.alias('to_user'))
                     .join(ToUserCategory, on=to_uc_join.alias('tuc'))
                     .join(ToCategory, on=to_c_join.alias('category'))
                     .order_by(Relationship.id)
                     .aggregate_rows())

            results = []
            for obj in query:
                from_user = obj.from_user
                to_user = obj.to_user
                results.append((
                    from_user.username,
                    from_user.fuc[0].category.name,
                    to_user.username,
                    to_user.tuc[0].category.name))

            self.assertEqual(results, [
                ('charlie', 'human', 'huey', 'kitty'),
                ('charlie', 'human', 'zaizee', 'kitty'),
                ('huey', 'kitty', 'charlie', 'human'),
                ('zaizee', 'kitty', 'charlie', 'human'),
            ])


class TestAggregateRowsRegression(ModelTestCase):
    requires = [
        User,
        Blog,
        Comment,
        Category,
        CommentCategory,
        BlogData]

    def setUp(self):
        super(TestAggregateRowsRegression, self).setUp()
        u = User.create(username='u1')
        b = Blog.create(title='b1', user=u)
        BlogData.create(blog=b)

        c1 = Comment.create(blog=b, comment='c1')
        c2 = Comment.create(blog=b, comment='c2')

        cat1 = Category.create(name='cat1')
        cat2 = Category.create(name='cat2')

        CommentCategory.create(category=cat1, comment=c1, sort_order=1)
        CommentCategory.create(category=cat2, comment=c1, sort_order=1)
        CommentCategory.create(category=cat1, comment=c2, sort_order=2)
        CommentCategory.create(category=cat2, comment=c2, sort_order=2)

    def test_aggregate_rows_regression(self):
        comments = (Comment
                    .select(
                        Comment,
                        CommentCategory,
                        Category,
                        Blog,
                        BlogData)
                    .join(CommentCategory, JOIN.LEFT_OUTER)
                    .join(Category, JOIN.LEFT_OUTER)
                    .switch(Comment)
                    .join(Blog)
                    .join(BlogData, JOIN.LEFT_OUTER)
                    .where(Category.id == 1)
                    .order_by(CommentCategory.sort_order))

        with self.assertQueryCount(1):
            c_list = list(comments.aggregate_rows())

    def test_regression_506(self):
        user = User.create(username='u2')
        for i in range(2):
            Blog.create(title='u2-%s' % i, user=user)

        users = (User
                 .select()
                 .order_by(User.id.desc())
                 .paginate(1, 5)
                 .alias('users'))

        with self.assertQueryCount(1):
            query = (User
                     .select(User, Blog)
                     .join(Blog)
                     .join(users, on=(User.id == users.c.id))
                     .order_by(User.username, Blog.title)
                     .aggregate_rows())

            results = []
            for user in query:
                results.append((
                    user.username,
                    [blog.title for blog in user.blog_set]))

        self.assertEqual(results, [
            ('u1', ['b1']),
            ('u2', ['u2-0', 'u2-1']),
        ])


class TestPrefetchNonPKFK(ModelTestCase):
    requires = [Package, PackageItem]
    data = {
        '101': ['a', 'b'],
        '102': ['c'],
        '103': [],
        '104': ['a', 'b', 'c', 'd', 'e'],
    }

    def setUp(self):
        super(TestPrefetchNonPKFK, self).setUp()
        for barcode, titles in self.data.items():
            Package.create(barcode=barcode)
            for title in titles:
                PackageItem.create(package=barcode, title=title)

    def test_prefetch(self):
        packages = Package.select().order_by(Package.barcode)
        items = PackageItem.select().order_by(PackageItem.id)
        query = prefetch(packages, items)

        for package, (barcode, titles) in zip(query, sorted(self.data.items())):
            self.assertEqual(package.barcode, barcode)
            self.assertEqual(
                [item.title for item in package.items_prefetch],
                titles)

        packages = (Package
                    .select()
                    .where(Package.barcode << ['101', '104'])
                    .order_by(Package.id))
        items = items.where(PackageItem.title << ['a', 'c', 'e'])
        query = prefetch(packages, items)
        accum = {}
        for package in query:
            accum[package.barcode] = [
                item.title for item in package.items_prefetch]

        self.assertEqual(accum, {
            '101': ['a'],
            '104': ['a', 'c','e'],
        })
