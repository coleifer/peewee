import sys

from peewee import ModelQueryResultWrapper
from peewee import NaiveQueryResultWrapper
from playhouse.tests.base import ModelTestCase
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

            another_iter = [u.username for u in qr]
            self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

            another_iter = [u.username for u in qr]
            self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

    def test_iteration_protocol(self):
        User.create_users(3)

        with self.assertQueryCount(1):
            query = User.select().order_by(User.id)
            qr = query.execute()
            for user in qr:
                pass

            self.assertRaises(StopIteration, next, qr)
            self.assertEqual([u.username for u in qr], ['u1', 'u2', 'u3'])
            self.assertEqual(query[0].username, 'u1')
            self.assertEqual(query[2].username, 'u3')
            self.assertRaises(StopIteration, next, qr)

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

        self.assertRaises(IndexError, uq.__getitem__, 10)
        self.assertRaises(ValueError, uq.__getitem__, -1)

        with self.assertQueryCount(0):
            res = uq[10:]
            self.assertEqual(res, [])

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
            join_expr = (User.id == Blog.user).alias('user')
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
