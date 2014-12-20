# encoding=utf-8

import datetime
import decimal
import itertools
import logging
import operator
import os
import threading
import time
import unittest
import sys
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
from contextlib import contextmanager
from functools import wraps

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from peewee import *
from peewee import AliasMap
from peewee import DeleteQuery
from peewee import InsertQuery
from peewee import logger
from peewee import ModelQueryResultWrapper
from peewee import NaiveQueryResultWrapper
from peewee import prefetch_add_subquery
from peewee import print_
from peewee import QueryCompiler
from peewee import R
from peewee import RawQuery
from peewee import SelectQuery
from peewee import sort_models_topologically
from peewee import transaction
from peewee import UpdateQuery


if sys.version_info[0] < 3:
    import codecs
    ulit = lambda s: codecs.unicode_escape_decode(s)[0]
    binary_construct = buffer
    binary_types = buffer
else:
    ulit = lambda s: s
    binary_construct = lambda s: bytes(s.encode('raw_unicode_escape'))
    binary_types = (bytes, memoryview)


class HelperMethodTestCase(BasePeeweeTestCase):
    def test_assert_query_count(self):
        def execute_queries(n):
            for i in range(n):
                test_db.execute_sql('select 1;')

        with self.assertQueryCount(0):
            pass

        with self.assertQueryCount(1):
            execute_queries(1)

        with self.assertQueryCount(2):
            execute_queries(2)

        def fails_low():
            with self.assertQueryCount(2):
                execute_queries(1)

        def fails_high():
            with self.assertQueryCount(1):
                execute_queries(2)

        self.assertRaises(AssertionError, fails_low)
        self.assertRaises(AssertionError, fails_high)



#
# TEST CASE USED TO PROVIDE ACCESS TO DATABASE
# FOR EXECUTION OF "LIVE" QUERIES
#

class ModelTestCase(BasePeeweeTestCase):
    requires = None

    def setUp(self):
        super(ModelTestCase, self).setUp()
        drop_tables(self.requires)
        create_tables(self.requires)

    def tearDown(self):
        drop_tables(self.requires)

    def create_user(self, username):
        return User.create(username=username)

    def create_users(self, n):
        for i in range(n):
            self.create_user('u%d' % (i + 1))



class NonPKFKBasicTestCase(ModelTestCase):
    requires = [Package, PackageItem]

    def setUp(self):
        super(NonPKFKBasicTestCase, self).setUp()

        for barcode in ['101', '102']:
            Package.create(barcode=barcode)
            for i in range(2):
                PackageItem.create(
                    package=barcode,
                    title='%s-%s' % (barcode, i))

    def test_fk_resolution(self):
        pi = PackageItem.get(PackageItem.title == '101-0')
        self.assertEqual(pi._data['package'], '101')
        self.assertEqual(pi.package, Package.get(Package.barcode == '101'))

    def test_select_generation(self):
        p = Package.get(Package.barcode == '101')
        self.assertEqual(
            [item.title for item in p.items.order_by(PackageItem.title)],
            ['101-0', '101-1'])

class ModelQueryTestCase(ModelTestCase):
    requires = [User, Blog]

    def setUp(self):
        super(ModelQueryTestCase, self).setUp()
        self._orig_db_insert_many = test_db.insert_many

    def tearDown(self):
        super(ModelQueryTestCase, self).tearDown()
        test_db.insert_many = self._orig_db_insert_many

    def create_users_blogs(self, n=10, nb=5):
        for i in range(n):
            u = User.create(username='u%d' % i)
            for j in range(nb):
                b = Blog.create(title='b-%d-%d' % (i, j), content=str(j), user=u)

    def test_select(self):
        self.create_users_blogs()

        users = User.select().where(User.username << ['u0', 'u5']).order_by(User.username)
        self.assertEqual([u.username for u in users], ['u0', 'u5'])

        blogs = Blog.select().join(User).where(
            (User.username << ['u0', 'u3']) &
            (Blog.content == '4')
        ).order_by(Blog.title)
        self.assertEqual([b.title for b in blogs], ['b-0-4', 'b-3-4'])

        users = User.select().paginate(2, 3)
        self.assertEqual([u.username for u in users], ['u3', 'u4', 'u5'])

    def test_select_all(self):
        self.create_users_blogs(2, 2)
        all_cols = SQL('*')
        query = Blog.select(all_cols)
        blogs = [blog for blog in query.order_by(Blog.pk)]
        self.assertEqual(
            [b.title for b in blogs],
            ['b-0-0', 'b-0-1', 'b-1-0', 'b-1-1'])
        self.assertEqual(
            [b.user.username for b in blogs],
            ['u0', 'u0', 'u1', 'u1'])

    def test_select_subquery(self):
        # 10 users, 5 blogs each
        self.create_users_blogs(5, 3)

        # delete user 2's 2nd blog
        Blog.delete().where(Blog.title == 'b-2-2').execute()

        subquery = Blog.select(fn.Count(Blog.pk)).where(Blog.user == User.id).group_by(Blog.user)
        users = User.select(User, subquery.alias('ct')).order_by(R('ct'), User.id)

        self.assertEqual([(x.username, x.ct) for x in users], [
            ('u2', 2),
            ('u0', 3),
            ('u1', 3),
            ('u3', 3),
            ('u4', 3),
        ])

    def test_scalar(self):
        self.create_users(5)

        users = User.select(fn.Count(User.id)).scalar()
        self.assertEqual(users, 5)

        users = User.select(fn.Count(User.id)).where(User.username << ['u1', 'u2'])
        self.assertEqual(users.scalar(), 2)
        self.assertEqual(users.scalar(True), (2,))

        users = User.select(fn.Count(User.id)).where(User.username == 'not-here')
        self.assertEqual(users.scalar(), 0)
        self.assertEqual(users.scalar(True), (0,))

        users = User.select(fn.Count(User.id), fn.Count(User.username))
        self.assertEqual(users.scalar(), 5)
        self.assertEqual(users.scalar(True), (5, 5))

        User.create(username='u1')
        User.create(username='u2')
        User.create(username='u3')
        User.create(username='u99')
        users = User.select(fn.Count(fn.Distinct(User.username))).scalar()
        self.assertEqual(users, 6)

    def test_update(self):
        self.create_users(5)
        uq = User.update(username='u-edited').where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u1', 'u2', 'u3', 'u4', 'u5'])

        uq.execute()
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u-edited', 'u-edited', 'u-edited', 'u4', 'u5'])

        self.assertRaises(KeyError, User.update, doesnotexist='invalid')

    def test_update_subquery(self):
        self.create_users(3)
        u1, u2, u3 = [user for user in User.select().order_by(User.id)]
        for i in range(4):
            Blog.create(title='b%s' % i, user=u1)
        for i in range(2):
            Blog.create(title='b%s' % i, user=u3)

        subquery = Blog.select(fn.COUNT(Blog.pk)).where(Blog.user == User.id)
        query = User.update(username=subquery)
        sql, params = normal_compiler.generate_update(query)
        self.assertEqual(sql, (
            'UPDATE "users" SET "username" = ('
            'SELECT COUNT("t2"."pk") FROM "blog" AS t2 '
            'WHERE ("t2"."user_id" = "users"."id"))'))
        self.assertEqual(query.execute(), 3)

        usernames = [u.username for u in User.select().order_by(User.id)]
        self.assertEqual(usernames, ['4', '0', '2'])

    def test_insert(self):
        iq = User.insert(username='u1')
        self.assertEqual(User.select().count(), 0)
        uid = iq.execute()
        self.assertTrue(uid > 0)
        self.assertEqual(User.select().count(), 1)
        u = User.get(User.id==uid)
        self.assertEqual(u.username, 'u1')

        iq = User.insert(doesnotexist='invalid')
        self.assertRaises(KeyError, iq.execute)

    def test_insert_from(self):
        u0, u1, u2 = [User.create(username='U%s' % i) for i in range(3)]

        subquery = (User
                    .select(fn.LOWER(User.username))
                    .where(User.username << ['U0', 'U2']))
        iq = User.insert_from([User.username], subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'SELECT LOWER("t2"."username") FROM "users" AS t2 '
            'WHERE ("t2"."username" IN (?, ?))'))
        self.assertEqual(params, ['U0', 'U2'])

        iq.execute()
        usernames = sorted([u.username for u in User.select()])
        self.assertEqual(usernames, ['U0', 'U1', 'U2', 'u0', 'u2'])

    def test_insert_many(self):
        qc = len(self.queries())
        iq = User.insert_many([
            {'username': 'u1'},
            {'username': 'u2'},
            {'username': 'u3'},
            {'username': 'u4'}])
        self.assertTrue(iq.execute())

        qc2 = len(self.queries())
        if test_db.insert_many:
            self.assertEqual(qc2 - qc, 1)
        else:
            self.assertEqual(qc2 - qc, 4)
        self.assertEqual(User.select().count(), 4)

        sq = User.select(User.username).order_by(User.username)
        self.assertEqual([u.username for u in sq], ['u1', 'u2', 'u3', 'u4'])

        iq = User.insert_many([{'username': 'u5'}])
        self.assertTrue(iq.execute())
        self.assertEqual(User.select().count(), 5)

        iq = User.insert_many([
            {User.username: 'u6'},
            {User.username: 'u7'},
            {'username': 'u8'}]).execute()

        sq = User.select(User.username).order_by(User.username)
        self.assertEqual([u.username for u in sq],
                         ['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7', 'u8'])

    def test_insert_many_fallback(self):
        # Simulate database not supporting multiple insert (older versions of
        # sqlite).
        test_db.insert_many = False
        with self.assertQueryCount(4):
            iq = User.insert_many([
                {'username': 'u1'},
                {'username': 'u2'},
                {'username': 'u3'},
                {'username': 'u4'}])
            self.assertTrue(iq.execute())

        self.assertEqual(User.select().count(), 4)

    def test_delete(self):
        self.create_users(5)
        dq = User.delete().where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual(User.select().count(), 5)
        nr = dq.execute()
        self.assertEqual(nr, 3)
        self.assertEqual([u.username for u in User.select()], ['u4', 'u5'])

    def test_raw(self):
        self.create_users(3)

        with self.assertQueryCount(1):
            rq = User.raw(
                'select * from users where username IN (%s,%s)' % (INT,INT),
                'u1', 'u3')
            self.assertEqual([u.username for u in rq], ['u1', 'u3'])

            # iterate again
            self.assertEqual([u.username for u in rq], ['u1', 'u3'])

        rq = User.raw(
            'select id, username, %s as secret from users where username = %s' % (INT,INT),
            'sh', 'u2')
        self.assertEqual([u.secret for u in rq], ['sh'])
        self.assertEqual([u.username for u in rq], ['u2'])

        rq = User.raw('select count(id) from users')
        self.assertEqual(rq.scalar(), 3)

        rq = User.raw('select username from users').tuples()
        self.assertEqual([r for r in rq], [
            ('u1',), ('u2',), ('u3',),
        ])

    def test_limits_offsets(self):
        for i in range(10):
            self.create_user(username='u%d' % i)
        sq = User.select().order_by(User.id)

        offset_no_lim = sq.offset(3)
        self.assertEqual(
            [u.username for u in offset_no_lim],
            ['u%d' % i for i in range(3, 10)]
        )

        offset_with_lim = sq.offset(5).limit(3)
        self.assertEqual(
            [u.username for u in offset_with_lim],
            ['u%d' % i for i in range(5, 8)]
        )

    def test_raw_fn(self):
        self.create_users_blogs(3, 2)  # 3 users, 2 blogs each.
        query = User.raw('select count(1) as ct from blog group by user_id')
        results = [x.ct for x in query]
        self.assertEqual(results, [2, 2, 2])


class ModelAPITestCase(ModelTestCase):
    requires = [User, Blog, Category, UserCategory]

    def test_related_name(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')
        b11 = Blog.create(user=u1, title='b11')
        b12 = Blog.create(user=u1, title='b12')
        b2 = Blog.create(user=u2, title='b2')

        self.assertEqual(
            [b.title for b in u1.blog_set.order_by(Blog.title)],
            ['b11', 'b12'])
        self.assertEqual(
            [b.title for b in u2.blog_set.order_by(Blog.title)],
            ['b2'])

    def test_related_name_collision(self):
        class Foo(TestModel):
            f1 = CharField()

        def make_klass():
            class FooRel(TestModel):
                foo = ForeignKeyField(Foo, related_name='f1')

        self.assertRaises(AttributeError, make_klass)

    def test_fk_exceptions(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(parent=c1, name='c2')
        self.assertEqual(c1.parent, None)
        self.assertEqual(c2.parent, c1)

        c2_db = Category.get(Category.id == c2.id)
        self.assertEqual(c2_db.parent, c1)

        u = self.create_user('u1')
        b = Blog.create(user=u, title='b')
        b2 = Blog(title='b2')

        self.assertEqual(b.user, u)
        self.assertRaises(User.DoesNotExist, getattr, b2, 'user')

    def test_fk_cache_invalidated(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')
        b = Blog.create(user=u1, title='b')

        blog = Blog.get(Blog.pk == b)
        with self.assertQueryCount(1):
            self.assertEqual(blog.user.id, u1.id)

        blog.user = u2.id
        with self.assertQueryCount(1):
            self.assertEqual(blog.user.id, u2.id)

        # No additional query.
        blog.user = u2.id
        with self.assertQueryCount(0):
            self.assertEqual(blog.user.id, u2.id)

    def test_fk_ints(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2', parent=c1.id)
        c2_db = Category.get(Category.id == c2.id)
        self.assertEqual(c2_db.parent, c1)

    def test_fk_caching(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2', parent=c1)
        c2_db = Category.get(Category.id == c2.id)

        with self.assertQueryCount(1):
            parent = c2_db.parent
            self.assertEqual(parent, c1)

            parent = c2_db.parent

    def test_category_select_related_alias(self):
        g1 = Category.create(name='g1')
        g2 = Category.create(name='g2')

        p1 = Category.create(name='p1', parent=g1)
        p2 = Category.create(name='p2', parent=g2)

        c1 = Category.create(name='c1', parent=p1)
        c11 = Category.create(name='c11', parent=p1)
        c2 = Category.create(name='c2', parent=p2)

        with self.assertQueryCount(1):
            Grandparent = Category.alias()
            Parent = Category.alias()
            sq = (Category
                  .select(Category, Parent, Grandparent)
                  .join(Parent, on=(Category.parent == Parent.id))
                  .join(Grandparent, on=(Parent.parent == Grandparent.id))
                  .where(Grandparent.name == 'g1')
                  .order_by(Category.name))

            self.assertEqual(
                [(c.name, c.parent.name, c.parent.parent.name) for c in sq],
                [('c1', 'p1', 'g1'), ('c11', 'p1', 'g1')])

    def test_creation(self):
        self.create_users(10)
        self.assertEqual(User.select().count(), 10)

    def test_saving(self):
        self.assertEqual(User.select().count(), 0)

        u = User(username='u1')
        self.assertEqual(u.save(), 1)
        u.username = 'u2'
        self.assertEqual(u.save(), 1)

        self.assertEqual(User.select().count(), 1)

        self.assertEqual(u.delete_instance(), 1)
        self.assertEqual(u.save(), 0)

    def test_modify_model_cause_it_dirty(self):
        u = User(username='u1')
        u.save()
        self.assertFalse(u.is_dirty())

        u.username = 'u2'
        self.assertTrue(u.is_dirty())
        self.assertEqual(u.dirty_fields, [User.username])

        u.save()
        self.assertFalse(u.is_dirty())

        b = Blog.create(user=u, title='b1')
        self.assertFalse(b.is_dirty())

        b.user = u
        self.assertTrue(b.is_dirty())
        self.assertEqual(b.dirty_fields, [Blog.user])

    def test_dirty_from_query(self):
        u1 = User.create(username='u1')
        b1 = Blog.create(title='b1', user=u1)
        b2 = Blog.create(title='b2', user=u1)

        u_db = User.get()
        self.assertFalse(u_db.is_dirty())

        b_with_u = (Blog
                    .select(Blog, User)
                    .join(User)
                    .where(Blog.title == 'b2')
                    .get())
        self.assertFalse(b_with_u.is_dirty())
        self.assertFalse(b_with_u.user.is_dirty())

        u_with_blogs = (User
                        .select(User, Blog)
                        .join(Blog)
                        .order_by(Blog.title)
                        .aggregate_rows())[0]
        self.assertFalse(u_with_blogs.is_dirty())
        for blog in u_with_blogs.blog_set:
            self.assertFalse(blog.is_dirty())

        b_with_users = (Blog
                        .select(Blog, User)
                        .join(User)
                        .order_by(Blog.title)
                        .aggregate_rows())
        b1, b2 = b_with_users
        self.assertFalse(b1.is_dirty())
        self.assertFalse(b1.user.is_dirty())
        self.assertFalse(b2.is_dirty())
        self.assertFalse(b2.user.is_dirty())

    def test_save_only(self):
        u = User.create(username='u')
        b = Blog.create(user=u, title='b1', content='ct')
        b.title = 'b1-edit'
        b.content = 'ct-edit'

        b.save(only=[Blog.title])

        b_db = Blog.get(Blog.pk == b.pk)
        self.assertEqual(b_db.title, 'b1-edit')
        self.assertEqual(b_db.content, 'ct')

        b = Blog(user=u, title='b2', content='foo')
        b.save(only=[Blog.user, Blog.title])

        b_db = Blog.get(Blog.pk == b.pk)

        self.assertEqual(b_db.title, 'b2')
        self.assertEqual(b_db.content, '')

    def test_save_only_dirty_fields(self):
        u = User.create(username='u1')
        b = Blog.create(title='b1', user=u, content='huey')
        b_db = Blog.get(Blog.pk == b.pk)
        b.title = 'baby huey'
        b.save(only=b.dirty_fields)
        b_db.content = 'mickey-nugget'
        b_db.save(only=b_db.dirty_fields)
        saved = Blog.get(Blog.pk == b.pk)
        self.assertEqual(saved.title, 'baby huey')
        self.assertEqual(saved.content, 'mickey-nugget')

    def test_zero_id(self):
        if isinstance(test_db, MySQLDatabase):
            # Need to explicitly tell MySQL it's OK to use zero.
            test_db.execute_sql("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'")
        query = 'insert into users (id, username) values (%s, %s)' % (
            test_db.interpolation, test_db.interpolation)
        test_db.execute_sql(query, (0, 'foo'))
        Blog.insert(title='foo2', user=0).execute()

        u = User.get(User.id == 0)
        b = Blog.get(Blog.user == u)

        self.assertTrue(u == u)
        self.assertTrue(u == b.user)

    def test_saving_via_create_gh111(self):
        u = User.create(username='u')
        b = Blog.create(title='foo', user=u)
        last_sql, _ = self.queries()[-1]
        self.assertFalse('pub_date' in last_sql)
        self.assertEqual(b.pub_date, None)

        b2 = Blog(title='foo2', user=u)
        b2.save()
        last_sql, _ = self.queries()[-1]
        self.assertFalse('pub_date' in last_sql)
        self.assertEqual(b2.pub_date, None)

    def test_reading(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')

        self.assertEqual(u1, User.get(username='u1'))
        self.assertEqual(u2, User.get(username='u2'))
        self.assertFalse(u1 == u2)

        self.assertEqual(u1, User.get(User.username == 'u1'))
        self.assertEqual(u2, User.get(User.username == 'u2'))

    def test_get_or_create(self):
        u1 = User.get_or_create(username='u1')
        u1_x = User.get_or_create(username='u1')
        self.assertEqual(u1.id, u1_x.id)
        self.assertEqual(User.select().count(), 1)

    def test_first(self):
        users = self.create_users(5)

        with self.assertQueryCount(1):
            sq = User.select().order_by(User.username)
            qr = sq.execute()

            # call it once
            first = sq.first()
            self.assertEqual(first.username, 'u1')

            # check the result cache
            self.assertEqual(len(qr._result_cache), 1)

            # call it again and we get the same result, but not an
            # extra query
            self.assertEqual(sq.first().username, 'u1')

        with self.assertQueryCount(0):
            usernames = [u.username for u in sq]
            self.assertEqual(usernames, ['u1', 'u2', 'u3', 'u4', 'u5'])

        with self.assertQueryCount(0):
            # call after iterating
            self.assertEqual(sq.first().username, 'u1')

            usernames = [u.username for u in sq]
            self.assertEqual(usernames, ['u1', 'u2', 'u3', 'u4', 'u5'])

        # call it with an empty result
        sq = User.select().where(User.username == 'not-here')
        self.assertEqual(sq.first(), None)

    def test_deleting(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')

        self.assertEqual(User.select().count(), 2)
        u1.delete_instance()
        self.assertEqual(User.select().count(), 1)

        self.assertEqual(u2, User.get(User.username=='u2'))

    def test_counting(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        for u in [u1, u2]:
            for i in range(5):
                Blog.create(title='b-%s-%s' % (u.username, i), user=u)

        uc = User.select().where(User.username == 'u1').join(Blog).count()
        self.assertEqual(uc, 5)

        uc = User.select().where(User.username == 'u1').join(Blog).distinct().count()
        self.assertEqual(uc, 1)

        self.assertEqual(Blog.select().limit(4).offset(3).count(), 4)
        self.assertEqual(Blog.select().limit(4).offset(3).count(True), 10)

        # Calling `distinct()` will result in a call to wrapped_count().
        uc = User.select().join(Blog).distinct().count()
        self.assertEqual(uc, 2)

        # Test with clear limit = True.
        self.assertEqual(User.select().limit(1).count(clear_limit=True), 2)
        self.assertEqual(
            User.select().limit(1).wrapped_count(clear_limit=True), 2)

        # Test with clear limit = False.
        self.assertEqual(User.select().limit(1).count(clear_limit=False), 1)
        self.assertEqual(
            User.select().limit(1).wrapped_count(clear_limit=False), 1)

    def test_ordering(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u2')
        users = User.select().order_by(User.username.desc(), User.id.desc())
        self.assertEqual([u._get_pk_value() for u in users], [u3.id, u2.id, u1.id])

    def test_count_transaction(self):
        for i in range(10):
            self.create_user(username='u%d' % i)

        with transaction(test_db):
            for user in SelectQuery(User):
                for i in range(20):
                    Blog.create(user=user, title='b-%d-%d' % (user.id, i))

        count = SelectQuery(Blog).count()
        self.assertEqual(count, 200)

    def test_exists(self):
        u1 = User.create(username='u1')
        self.assertTrue(User.select().where(User.username == 'u1').exists())
        self.assertFalse(User.select().where(User.username == 'u2').exists())

    def test_unicode(self):
        # create a unicode literal
        ustr = ulit('Lýðveldið Ísland')
        u = self.create_user(username=ustr)

        # query using the unicode literal
        u_db = User.get(User.username == ustr)

        # the db returns a unicode literal
        self.assertEqual(u_db.username, ustr)

        # delete the user
        self.assertEqual(u.delete_instance(), 1)

        # convert the unicode to a utf8 string
        utf8_str = ustr.encode('utf-8')

        # create using the utf8 string
        u2 = self.create_user(username=utf8_str)

        # query using unicode literal
        u2_db = User.get(User.username == ustr)

        # we get unicode back
        self.assertEqual(u2_db.username, ustr)

    def test_unicode_issue202(self):
        ustr = ulit('M\u00f6rk')
        user = User.create(username=ustr)
        self.assertEqual(user.username, ustr)


class TestMultipleForeignKey(ModelTestCase):
    requires = [Manufacturer, Component, Computer]
    test_values = [
        ['3TB', '16GB', 'i7'],
        ['128GB', '1GB', 'ARM'],
    ]

    def setUp(self):
        super(TestMultipleForeignKey, self).setUp()
        intel = Manufacturer.create(name='Intel')
        amd = Manufacturer.create(name='AMD')
        kingston = Manufacturer.create(name='Kingston')
        for hard_drive, memory, processor in self.test_values:
            c = Computer.create(
                hard_drive=Component.create(name=hard_drive),
                memory=Component.create(name=memory, manufacturer=kingston),
                processor=Component.create(name=processor, manufacturer=intel))

        # The 2nd computer has an AMD processor.
        c.processor.manufacturer = amd
        c.processor.save()

    def test_multi_join(self):
        HDD = Component.alias()
        HDDMf = Manufacturer.alias()
        Memory = Component.alias()
        MemoryMf = Manufacturer.alias()
        Processor = Component.alias()
        ProcessorMf = Manufacturer.alias()
        query = (Computer
                 .select(
                     Computer,
                     HDD,
                     Memory,
                     Processor,
                     HDDMf,
                     MemoryMf,
                     ProcessorMf)
                 .join(HDD, on=(
                     Computer.hard_drive == HDD.id).alias('hard_drive'))
                 .join(
                     HDDMf,
                     JOIN_LEFT_OUTER,
                     on=(HDD.manufacturer == HDDMf.id))
                 .switch(Computer)
                 .join(Memory, on=(
                     Computer.memory == Memory.id).alias('memory'))
                 .join(
                     MemoryMf,
                     JOIN_LEFT_OUTER,
                     on=(Memory.manufacturer == MemoryMf.id))
                 .switch(Computer)
                 .join(Processor, on=(
                     Computer.processor == Processor.id).alias('processor'))
                 .join(
                     ProcessorMf,
                     JOIN_LEFT_OUTER,
                     on=(Processor.manufacturer == ProcessorMf.id))
                 .order_by(Computer.id))

        with self.assertQueryCount(1):
            vals = []
            manufacturers = []
            for computer in query:
                components = [
                    computer.hard_drive,
                    computer.memory,
                    computer.processor]
                vals.append([component.name for component in components])
                for component in components:
                    if component.manufacturer:
                        manufacturers.append(component.manufacturer.name)
                    else:
                        manufacturers.append(None)

            self.assertEqual(vals, self.test_values)
            self.assertEqual(manufacturers, [
                None, 'Kingston', 'Intel',
                None, 'Kingston', 'AMD',
            ])


class ModelAggregateTestCase(ModelTestCase):
    requires = [OrderedModel, User, Blog]

    def create_ordered_models(self):
        return [
            OrderedModel.create(
                title=i, created=datetime.datetime(2013, 1, i + 1))
            for i in range(3)]

    def create_user_blogs(self):
        users = []
        ct = 0
        for i in range(2):
            user = User.create(username='u-%d' % i)
            for j in range(2):
                ct += 1
                Blog.create(
                    user=user,
                    title='b-%d-%d' % (i, j),
                    pub_date=datetime.datetime(2013, 1, ct))
            users.append(user)
        return users

    def test_annotate_int(self):
        users = self.create_user_blogs()
        annotated = User.select().annotate(Blog, fn.Count(Blog.pk).alias('ct'))
        for i, user in enumerate(annotated):
            self.assertEqual(user.ct, 2)
            self.assertEqual(user.username, 'u-%d' % i)

    def test_annotate_datetime(self):
        users = self.create_user_blogs()
        annotated = (User
                     .select()
                     .annotate(Blog, fn.Max(Blog.pub_date).alias('max_pub')))
        user_0, user_1 = annotated
        self.assertEqual(user_0.max_pub, datetime.datetime(2013, 1, 2))
        self.assertEqual(user_1.max_pub, datetime.datetime(2013, 1, 4))

    def test_aggregate_int(self):
        models = self.create_ordered_models()
        max_id = OrderedModel.select().aggregate(fn.Max(OrderedModel.id))
        self.assertEqual(max_id, models[-1].id)

    def test_aggregate_datetime(self):
        models = self.create_ordered_models()
        max_created = (OrderedModel
                       .select()
                       .aggregate(fn.Max(OrderedModel.created)))
        self.assertEqual(max_created, models[-1].created)


class FromMultiTableTestCase(ModelTestCase):
    requires = [Blog, Comment, User]

    def setUp(self):
        super(FromMultiTableTestCase, self).setUp()

        for u in range(2):
            user = User.create(username='u%s' % u)
            for i in range(3):
                b = Blog.create(user=user, title='b%s-%s' % (u, i))
                for j in range(i):
                    Comment.create(blog=b, comment='c%s-%s' % (i, j))

    def test_from_multi_table(self):
        q = (Blog
             .select(Blog, User)
             .from_(Blog, User)
             .where(
                 (Blog.user == User.id) &
                 (User.username == 'u0'))
             .order_by(Blog.pk)
             .naive())

        with self.assertQueryCount(1):
            blogs = [b.title for b in q]
            self.assertEqual(blogs, ['b0-0', 'b0-1', 'b0-2'])

            usernames = [b.username for b in q]
            self.assertEqual(usernames, ['u0', 'u0', 'u0'])

    def test_subselect(self):
        inner = User.select(User.username)
        self.assertEqual(
            [u.username for u in inner.order_by(User.username)], ['u0', 'u1'])

        # Have to manually specify the alias as "t1" because the outer query
        # will expect that.
        outer = (User
                 .select(User.username)
                 .from_(inner.alias('t1')))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT "users"."username" FROM '
            '(SELECT "users"."username" FROM "users" AS users) AS t1'))

        self.assertEqual(
            [u.username for u in outer.order_by(User.username)], ['u0', 'u1'])

    def test_subselect_with_column(self):
        inner = User.select(User.username.alias('name')).alias('t1')
        outer = (User
                 .select(inner.c.name)
                 .from_(inner))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT "t1"."name" FROM '
            '(SELECT "users"."username" AS name FROM "users" AS users) AS t1'))

        query = outer.order_by(inner.c.name.desc())
        self.assertEqual([u[0] for u in query.tuples()], ['u1', 'u0'])

    def test_subselect_with_join(self):
        inner = User.select(User.id, User.username).alias('q1')
        outer = (Blog
                 .select(inner.c.id, inner.c.username)
                 .from_(inner)
                 .join(Comment, on=(inner.c.id == Comment.id)))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT "q1"."id", "q1"."username" FROM ('
            'SELECT "users"."id", "users"."username" FROM "users" AS users) AS q1 '
            'INNER JOIN "comment" AS comment ON ("q1"."id" = "comment"."id")'))

    def test_join_on_query(self):
        u0 = User.get(User.username == 'u0')
        u1 = User.get(User.username == 'u1')

        inner = User.select().alias('j1')
        outer = (Blog
                 .select(Blog.title, Blog.user)
                 .join(inner, on=(Blog.user == inner.c.id))
                 .order_by(Blog.pk))
        res = [row for row in outer.tuples()]
        self.assertEqual(res, [
            ('b0-0', u0.id),
            ('b0-1', u0.id),
            ('b0-2', u0.id),
            ('b1-0', u1.id),
            ('b1-1', u1.id),
            ('b1-2', u1.id),
        ])

class RecursiveDeleteTestCase(ModelTestCase):
    requires = [
        Parent, Child, Orphan, ChildPet, OrphanPet, Package, PackageItem]

    def setUp(self):
        super(RecursiveDeleteTestCase, self).setUp()
        p1 = Parent.create(data='p1')
        p2 = Parent.create(data='p2')
        c11 = Child.create(parent=p1)
        c12 = Child.create(parent=p1)
        c21 = Child.create(parent=p2)
        c22 = Child.create(parent=p2)
        o11 = Orphan.create(parent=p1)
        o12 = Orphan.create(parent=p1)
        o21 = Orphan.create(parent=p2)
        o22 = Orphan.create(parent=p2)
        ChildPet.create(child=c11)
        ChildPet.create(child=c12)
        ChildPet.create(child=c21)
        ChildPet.create(child=c22)
        OrphanPet.create(orphan=o11)
        OrphanPet.create(orphan=o12)
        OrphanPet.create(orphan=o21)
        OrphanPet.create(orphan=o22)
        self.p1 = p1
        self.p2 = p2

    def test_recursive_update(self):
        self.p1.delete_instance(recursive=True)
        counts = (
            #query,fk,p1,p2,tot
            (Child.select(), Child.parent, 0, 2, 2),
            (Orphan.select(), Orphan.parent, 0, 2, 4),
            (ChildPet.select().join(Child), Child.parent, 0, 2, 2),
            (OrphanPet.select().join(Orphan), Orphan.parent, 0, 2, 4),
        )

        for query, fk, p1_ct, p2_ct, tot in counts:
            self.assertEqual(query.where(fk == self.p1).count(), p1_ct)
            self.assertEqual(query.where(fk == self.p2).count(), p2_ct)
            self.assertEqual(query.count(), tot)

    def test_recursive_delete(self):
        self.p1.delete_instance(recursive=True, delete_nullable=True)
        counts = (
            #query,fk,p1,p2,tot
            (Child.select(), Child.parent, 0, 2, 2),
            (Orphan.select(), Orphan.parent, 0, 2, 2),
            (ChildPet.select().join(Child), Child.parent, 0, 2, 2),
            (OrphanPet.select().join(Orphan), Orphan.parent, 0, 2, 2),
        )

        for query, fk, p1_ct, p2_ct, tot in counts:
            self.assertEqual(query.where(fk == self.p1).count(), p1_ct)
            self.assertEqual(query.where(fk == self.p2).count(), p2_ct)
            self.assertEqual(query.count(), tot)

    def test_recursive_non_pk_fk(self):
        for i in range(3):
            Package.create(barcode=str(i))
            for j in range(4):
                PackageItem.create(package=str(i), title='%s-%s' % (i, j))

        self.assertEqual(Package.select().count(), 3)
        self.assertEqual(PackageItem.select().count(), 12)

        Package.get(Package.barcode == '1').delete_instance(recursive=True)

        self.assertEqual(Package.select().count(), 2)
        self.assertEqual(PackageItem.select().count(), 8)

        items = (PackageItem
                 .select(PackageItem.title)
                 .order_by(PackageItem.id)
                 .tuples())
        self.assertEqual([i[0] for i in items], [
            '0-0', '0-1', '0-2', '0-3',
            '2-0', '2-1', '2-2', '2-3',
        ])


class MultipleFKTestCase(ModelTestCase):
    requires = [User, Relationship]

    def test_multiple_fks(self):
        a = User.create(username='a')
        b = User.create(username='b')
        c = User.create(username='c')

        self.assertEqual(list(a.relationships), [])
        self.assertEqual(list(a.related_to), [])

        r_ab = Relationship.create(from_user=a, to_user=b)
        self.assertEqual(list(a.relationships), [r_ab])
        self.assertEqual(list(a.related_to), [])
        self.assertEqual(list(b.relationships), [])
        self.assertEqual(list(b.related_to), [r_ab])

        r_bc = Relationship.create(from_user=b, to_user=c)

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == a)
        self.assertEqual(list(following), [b])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == a.id)
        self.assertEqual(list(followers), [])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == b.id)
        self.assertEqual(list(following), [c])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == b.id)
        self.assertEqual(list(followers), [a])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == c.id)
        self.assertEqual(list(following), [])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == c.id)
        self.assertEqual(list(followers), [b])


class CompositeKeyTestCase(ModelTestCase):
    requires = [Tag, Post, TagPostThrough, CompositeKeyModel, User, UserThing]

    def setUp(self):
        super(CompositeKeyTestCase, self).setUp()
        tags = [Tag.create(tag='t%d' % i) for i in range(1, 4)]
        posts = [Post.create(title='p%d' % i) for i in range(1, 4)]
        p12 = Post.create(title='p12')
        for t, p in zip(tags, posts):
            TagPostThrough.create(tag=t, post=p)
        TagPostThrough.create(tag=tags[0], post=p12)
        TagPostThrough.create(tag=tags[1], post=p12)

    def test_create_table_query(self):
        query, params = compiler.create_table(TagPostThrough)
        self.assertEqual(
            query,
            'CREATE TABLE "tagpostthrough" '
            '("tag_id" INTEGER NOT NULL, '
            '"post_id" INTEGER NOT NULL, '
            'PRIMARY KEY ("tag_id", "post_id"), '
            'FOREIGN KEY ("tag_id") REFERENCES "tag" ("id"), '
            'FOREIGN KEY ("post_id") REFERENCES "post" ("id")'
            ')')

    def test_get_set_id(self):
        tpt = (TagPostThrough
               .select()
               .join(Tag)
               .switch(TagPostThrough)
               .join(Post)
               .order_by(Tag.tag, Post.title)).get()
        # Sanity check.
        self.assertEqual(tpt.tag.tag, 't1')
        self.assertEqual(tpt.post.title, 'p1')

        tag = Tag.select().where(Tag.tag == 't1').get()
        post = Post.select().where(Post.title == 'p1').get()
        self.assertEqual(tpt._get_pk_value(), (tag, post))

        # set_id is a no-op.
        tpt._set_pk_value(None)
        self.assertEqual(tpt._get_pk_value(), (tag, post))

    def test_querying(self):
        posts = (Post.select()
                 .join(TagPostThrough)
                 .join(Tag)
                 .where(Tag.tag == 't1')
                 .order_by(Post.title))
        self.assertEqual([p.title for p in posts], ['p1', 'p12'])

        tags = (Tag.select()
                .join(TagPostThrough)
                .join(Post)
                .where(Post.title == 'p12')
                .order_by(Tag.tag))
        self.assertEqual([t.tag for t in tags], ['t1', 't2'])

    def test_composite_key_model(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 2.0)]
        c1, c2, c3, c4 = [
            CKM.create(f1=f1, f2=f2, f3=f3) for f1, f2, f3 in values]

        # Update a single row, giving it a new value for `f3`.
        CKM.update(f3=3.0).where((CKM.f1 == 'a') & (CKM.f2 == 2)).execute()

        c = CKM.get((CKM.f1 == 'a') & (CKM.f2 == 2))
        self.assertEqual(c.f3, 3.0)

        # Update the `f3` value and call `save()`, triggering an update.
        c3.f3 = 4.0
        c3.save()

        c = CKM.get((CKM.f1 == 'b') & (CKM.f2 == 1))
        self.assertEqual(c.f3, 4.0)

        # Only 1 row updated.
        query = CKM.select().where(CKM.f3 == 4.0)
        self.assertEqual(query.wrapped_count(), 1)

        # Unfortunately this does not work since the original value of the
        # PK is lost (and hence cannot be used to update).
        c4.f1 = 'c'
        c4.save()
        self.assertRaises(
            CKM.DoesNotExist, CKM.get, (CKM.f1 == 'c') & (CKM.f2 == 2))

    def test_count_composite_key(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 1.0)]
        for f1, f2, f3 in values:
            CKM.create(f1=f1, f2=f2, f3=f3)

        self.assertEqual(CKM.select().wrapped_count(), 4)
        self.assertEqual(CKM.select().count(), 4)
        self.assertTrue(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 1)).exists())
        self.assertFalse(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 3)).exists())

    def test_delete_instance(self):
        u1, u2 = [User.create(username='u%s' % i) for i in range(2)]
        ut1 = UserThing.create(thing='t1', user=u1)
        ut2 = UserThing.create(thing='t2', user=u1)
        ut3 = UserThing.create(thing='t1', user=u2)
        ut4 = UserThing.create(thing='t3', user=u2)

        res = ut1.delete_instance()
        self.assertEqual(res, 1)
        self.assertEqual(
            [x.thing for x in UserThing.select().order_by(UserThing.thing)],
            ['t1', 't2', 't3'])


class ManyToManyTestCase(ModelTestCase):
    requires = [User, Category, UserCategory]

    def setUp(self):
        super(ManyToManyTestCase, self).setUp()
        users = ['u1', 'u2', 'u3']
        categories = ['c1', 'c2', 'c3', 'c12', 'c23']
        user_to_cat = {
            'u1': ['c1', 'c12'],
            'u2': ['c2', 'c12', 'c23'],
        }
        for u in users:
            User.create(username=u)
        for c in categories:
            Category.create(name=c)
        for user, categories in user_to_cat.items():
            user = User.get(User.username == user)
            for category in categories:
                UserCategory.create(
                    user=user,
                    category=Category.get(Category.name == category))

    def test_m2m(self):
        def aU(q, exp):
            self.assertEqual([u.username for u in q.order_by(User.username)], exp)
        def aC(q, exp):
            self.assertEqual([c.name for c in q.order_by(Category.name)], exp)

        users = User.select().join(UserCategory).join(Category).where(Category.name == 'c1')
        aU(users, ['u1'])

        users = User.select().join(UserCategory).join(Category).where(Category.name == 'c3')
        aU(users, [])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u1')
        aC(cats, ['c1', 'c12'])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u2')
        aC(cats, ['c12', 'c2', 'c23'])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u3')
        aC(cats, [])

        cats = Category.select().join(UserCategory).join(User).where(
            Category.name << ['c1', 'c2', 'c3']
        )
        aC(cats, ['c1', 'c2'])

        cats = Category.select().join(UserCategory, JOIN_LEFT_OUTER).join(User, JOIN_LEFT_OUTER).where(
            Category.name << ['c1', 'c2', 'c3']
        )
        aC(cats, ['c1', 'c2', 'c3'])

    def test_many_to_many_prefetch(self):
        categories = Category.select().order_by(Category.name)
        user_categories = UserCategory.select().order_by(UserCategory.id)
        users = User.select().order_by(User.username)
        results = {}
        result_list = []
        with self.assertQueryCount(3):
            query = prefetch(categories, user_categories, users)
            for category in query:
                results.setdefault(category.name, set())
                result_list.append(category.name)
                for user_category in category.usercategory_set_prefetch:
                    results[category.name].add(user_category.user.username)
                    result_list.append(user_category.user.username)

        self.assertEqual(results, {
            'c1': set(['u1']),
            'c12': set(['u1', 'u2']),
            'c2': set(['u2']),
            'c23': set(['u2']),
            'c3': set(),
        })
        self.assertEqual(
            sorted(result_list),
            ['c1', 'c12', 'c2', 'c23', 'c3', 'u1', 'u1', 'u2', 'u2', 'u2'])


class FieldTypeTestCase(ModelTestCase):
    requires = [NullModel, BlobModel]

    _dt = datetime.datetime
    _d = datetime.date
    _t = datetime.time

    _data = (
        ('char_field', 'text_field', 'int_field', 'float_field', 'decimal_field1', 'datetime_field', 'date_field', 'time_field'),
        ('c1',         't1',         1,           1.0,           "1.0",            _dt(2010, 1, 1),  _d(2010, 1, 1), _t(1, 0)),
        ('c2',         't2',         2,           2.0,           "2.0",            _dt(2010, 1, 2),  _d(2010, 1, 2), _t(2, 0)),
        ('c3',         't3',         3,           3.0,           "3.0",            _dt(2010, 1, 3),  _d(2010, 1, 3), _t(3, 0)),
    )

    def setUp(self):
        super(FieldTypeTestCase, self).setUp()
        self.field_data = {}

        headers = self._data[0]
        for row in self._data[1:]:
            nm = NullModel()
            for i, col in enumerate(row):
                attr = headers[i]
                self.field_data.setdefault(attr, [])
                self.field_data[attr].append(col)
                setattr(nm, attr, col)
            nm.save()

    def assertNM(self, q, exp):
        query = NullModel.select().where(q).order_by(NullModel.id)
        self.assertEqual([nm.char_field for nm in query], exp)

    def test_null_query(self):
        NullModel.delete().execute()
        nm1 = NullModel.create(char_field='nm1')
        nm2 = NullModel.create(char_field='nm2', int_field=1)
        nm3 = NullModel.create(char_field='nm3', int_field=2, float_field=3.0)

        q = ~(NullModel.int_field >> None)
        self.assertNM(q, ['nm2', 'nm3'])

    def test_field_types(self):
        for field, values in self.field_data.items():
            field_obj = getattr(NullModel, field)
            self.assertNM(field_obj < values[2], ['c1', 'c2'])
            self.assertNM(field_obj <= values[1], ['c1', 'c2'])
            self.assertNM(field_obj > values[0], ['c2', 'c3'])
            self.assertNM(field_obj >= values[1], ['c2', 'c3'])
            self.assertNM(field_obj == values[1], ['c2'])
            self.assertNM(field_obj != values[1], ['c1', 'c3'])
            self.assertNM(field_obj << [values[0], values[2]], ['c1', 'c3'])
            self.assertNM(field_obj << [values[1]], ['c2'])

    def test_charfield(self):
        NM = NullModel
        nm = NM.create(char_field=4)
        nm_db = NM.get(NM.id==nm.id)
        self.assertEqual(nm_db.char_field, '4')

        nm_alpha = NM.create(char_field='Alpha')
        nm_bravo = NM.create(char_field='Bravo')

        if isinstance(test_db, SqliteDatabase):
            # Sqlite's sql-dialect uses "*" as case-sensitive lookup wildcard,
            # and pysqlcipher is simply a wrapper around sqlite's engine.
            like_wildcard = '*'
        else:
            like_wildcard = '%'
        like_str = '%sA%s' % (like_wildcard, like_wildcard)
        ilike_str = '%A%'

        case_sens = NM.select(NM.char_field).where(NM.char_field % like_str)
        self.assertEqual([x[0] for x in case_sens.tuples()], ['Alpha'])

        case_insens = NM.select(NM.char_field).where(NM.char_field ** ilike_str)
        self.assertEqual([x[0] for x in case_insens.tuples()], ['Alpha', 'Bravo'])

    def test_intfield(self):
        nm = NullModel.create(int_field='4')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.int_field, 4)

    def test_floatfield(self):
        nm = NullModel.create(float_field='4.2')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.float_field, 4.2)

    def test_decimalfield(self):
        D = decimal.Decimal
        nm = NullModel()
        nm.decimal_field1 = D("3.14159265358979323")
        nm.decimal_field2 = D("100.33")
        nm.save()

        nm_from_db = NullModel.get(NullModel.id==nm.id)
        # sqlite doesn't enforce these constraints properly
        #self.assertEqual(nm_from_db.decimal_field1, decimal.Decimal("3.14159"))
        self.assertEqual(nm_from_db.decimal_field2, D("100.33"))

        class TestDecimalModel(TestModel):
            df1 = DecimalField(decimal_places=2, auto_round=True)
            df2 = DecimalField(decimal_places=2, auto_round=True, rounding=decimal.ROUND_UP)

        f1 = TestDecimalModel.df1.db_value
        f2 = TestDecimalModel.df2.db_value

        self.assertEqual(f1(D('1.2345')), D('1.23'))
        self.assertEqual(f2(D('1.2345')), D('1.24'))

    def test_boolfield(self):
        NullModel.delete().execute()

        nmt = NullModel.create(boolean_field=True, char_field='t')
        nmf = NullModel.create(boolean_field=False, char_field='f')
        nmn = NullModel.create(boolean_field=None, char_field='n')

        self.assertNM(NullModel.boolean_field == True, ['t'])
        self.assertNM(NullModel.boolean_field == False, ['f'])
        self.assertNM(NullModel.boolean_field >> None, ['n'])

    def _time_to_delta(self, t):
        micro = t.microsecond / 1000000.
        return datetime.timedelta(
            seconds=(3600 * t.hour) + (60 * t.minute) + t.second + micro)

    def test_date_and_time_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)
        td1 = self._time_to_delta(t1)
        td2 = self._time_to_delta(t2)

        nm1 = NullModel.create(datetime_field=dt1, date_field=d1, time_field=t1)
        nm2 = NullModel.create(datetime_field=dt2, time_field=t2)

        nmf1 = NullModel.get(NullModel.id==nm1.id)
        self.assertEqual(nmf1.date_field, d1)
        if isinstance(test_db, MySQLDatabase):
            # mysql doesn't store microseconds
            self.assertEqual(nmf1.datetime_field, dt2)
            self.assertEqual(nmf1.time_field, td2)
        else:
            self.assertEqual(nmf1.datetime_field, dt1)
            self.assertEqual(nmf1.time_field, t1)

        nmf2 = NullModel.get(NullModel.id==nm2.id)
        self.assertEqual(nmf2.datetime_field, dt2)
        if isinstance(test_db, MySQLDatabase):
            self.assertEqual(nmf2.time_field, td2)
        else:
            self.assertEqual(nmf2.time_field, t2)

    def test_date_as_string(self):
        nm1 = NullModel.create(date_field='2014-01-02')
        nm1_db = NullModel.get(NullModel.id == nm1.id)
        self.assertEqual(nm1_db.date_field, datetime.date(2014, 1, 2))

    def test_various_formats(self):
        class FormatModel(Model):
            dtf = DateTimeField()
            df = DateField()
            tf = TimeField()

        dtf = FormatModel._meta.fields['dtf']
        df = FormatModel._meta.fields['df']
        tf = FormatModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1, 11, 11, 11, 123456
        ))
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1, 11, 11, 11
        ))
        self.assertEqual(dtf.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(dtf.python_value('2012 01 01'), '2012 01 01')

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012 01 01'), '2012 01 01')

        t = datetime.time
        self.assertEqual(tf.python_value('2012-01-01 11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('2012-01-01 11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11'), t(
            11, 11,
        ))
        self.assertEqual(tf.python_value('11:11 AM'), '11:11 AM')

        class CustomFormatsModel(Model):
            dtf = DateTimeField(formats=['%b %d, %Y %I:%M:%S %p'])
            df = DateField(formats=['%b %d, %Y'])
            tf = TimeField(formats=['%I:%M %p'])

        dtf = CustomFormatsModel._meta.fields['dtf']
        df = CustomFormatsModel._meta.fields['df']
        tf = CustomFormatsModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), '2012-01-01 11:11:11.123456')
        self.assertEqual(dtf.python_value('Jan 1, 2012 11:11:11 PM'), d(
            2012, 1, 1, 23, 11, 11,
        ))

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01'), '2012-01-01')
        self.assertEqual(df.python_value('Jan 1, 2012'), d(
            2012, 1, 1,
        ))

        t = datetime.time
        self.assertEqual(tf.python_value('11:11:11'), '11:11:11')
        self.assertEqual(tf.python_value('11:11 PM'), t(
            23, 11
        ))

    def test_blob_field(self):
        byte_count = 256
        data = ''.join(chr(i) for i in range(256))
        blob = BlobModel.create(data=data)

        # pull from db and check binary data
        res = BlobModel.get(BlobModel.id == blob.id)
        self.assertTrue(isinstance(res.data, binary_types))

        self.assertEqual(len(res.data), byte_count)
        db_data = res.data
        binary_data = binary_construct(data)

        if db_data != binary_data and sys.version_info[:3] >= (3, 3, 3):
            db_data = db_data.tobytes()

        self.assertEqual(db_data, binary_data)

        # try querying the blob field
        binary_data = res.data

        # use the string representation
        res = BlobModel.get(BlobModel.data == data)
        self.assertEqual(res.id, blob.id)

        # use the binary representation
        res = BlobModel.get(BlobModel.data == binary_data)
        self.assertEqual(res.id, blob.id)

    def test_between(self):
        field = NullModel.int_field
        self.assertNM(field.between(1, 2), ['c1', 'c2'])
        self.assertNM(field.between(2, 3), ['c2', 'c3'])
        self.assertNM(field.between(5, 300), [])

    def test_in_(self):
        self.assertNM(NullModel.int_field.in_(1, 3), ['c1', 'c3'])
        self.assertNM(NullModel.int_field.in_(2, 5), ['c2'])

    def test_contains(self):
        self.assertNM(NullModel.char_field.contains('c2'), ['c2'])
        self.assertNM(NullModel.char_field.contains('c'), ['c1', 'c2', 'c3'])
        self.assertNM(NullModel.char_field.contains('1'), ['c1'])

    def test_startswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.startswith('c'), ['c1', 'c2', 'c3', 'ch1'])
        self.assertNM(NullModel.char_field.startswith('ch'), ['ch1'])
        self.assertNM(NullModel.char_field.startswith('a'), [])

    def test_endswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.endswith('1'), ['c1', 'ch1'])
        self.assertNM(NullModel.char_field.endswith('4'), [])

    def test_regexp(self):
        values = [
            'abcdefg',
            'abcd',
            'defg',
            'gij',
            'xx',
        ]
        for value in values:
            NullModel.create(char_field=value)

        def assertValues(regexp, *expected):
            query = NullModel.select().where(
                NullModel.char_field.regexp(regexp)).order_by(NullModel.id)
            values = [nm.char_field for nm in query]
            self.assertEqual(values, list(expected))

        assertValues('^ab', 'abcdefg', 'abcd')
        assertValues('d', 'abcdefg', 'abcd', 'defg')
        assertValues('efg$', 'abcdefg', 'defg')
        assertValues('a.+d', 'abcdefg', 'abcd')

    def test_concat(self):
        if database_class is MySQLDatabase:
            if TEST_VERBOSITY > 0:
                print_('Skipping `concat` for mysql.')
            return

        NullModel.create(char_field='foo')
        NullModel.create(char_field='bar')

        values = (NullModel
                  .select(
                      NullModel.char_field.concat('-nuggets').alias('nugs'))
                  .order_by(NullModel.id)
                  .dicts())
        self.assertEqual(list(values), [
            {'nugs': 'c1-nuggets'},
            {'nugs': 'c2-nuggets'},
            {'nugs': 'c3-nuggets'},
            {'nugs': 'foo-nuggets'},
            {'nugs': 'bar-nuggets'}])

class DateTimeExtractTestCase(ModelTestCase):
    requires = [NullModel]

    test_datetimes = [
        datetime.datetime(2001, 1, 2, 3, 4, 5),
        datetime.datetime(2002, 2, 3, 4, 5, 6),
        # overlap on year and hour with previous
        datetime.datetime(2002, 3, 4, 4, 6, 7),
    ]
    datetime_parts = ['year', 'month', 'day', 'hour', 'minute', 'second']
    date_parts = datetime_parts[:3]
    time_parts = datetime_parts[3:]

    def setUp(self):
        super(DateTimeExtractTestCase, self).setUp()

        self.nms = []
        for dt in self.test_datetimes:
            self.nms.append(NullModel.create(
                datetime_field=dt,
                date_field=dt.date(),
                time_field=dt.time()))

    def assertDates(self, sq, expected):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(e,) for e in expected])

    def assertPKs(self, sq, idxs):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(self.nms[i].id,) for i in idxs])

    def test_extract_datetime(self):
        self.test_extract_date(NullModel.datetime_field)
        self.test_extract_time(NullModel.datetime_field)

    def test_extract_date(self, f=None):
        if f is None:
            f = NullModel.date_field

        self.assertDates(NullModel.select(f.year), [2001, 2002, 2002])
        self.assertDates(NullModel.select(f.month), [1, 2, 3])
        self.assertDates(NullModel.select(f.day), [2, 3, 4])

    def test_extract_time(self, f=None):
        if f is None:
            f = NullModel.time_field

        self.assertDates(NullModel.select(f.hour), [3, 4, 4])
        self.assertDates(NullModel.select(f.minute), [4, 5, 6])
        self.assertDates(NullModel.select(f.second), [5, 6, 7])

    def test_extract_datetime_where(self):
        f = NullModel.datetime_field
        self.test_extract_date_where(f)
        self.test_extract_time_where(f)

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where((f.year == 2002) & (f.month == 2)), [1])
        self.assertPKs(sq.where((f.year == 2002) & (f.hour == 4)), [1, 2])
        self.assertPKs(sq.where((f.year == 2002) & (f.minute == 5)), [1])

    def test_extract_date_where(self, f=None):
        if f is None:
            f = NullModel.date_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.year == 2001), [0])
        self.assertPKs(sq.where(f.year == 2002), [1, 2])
        self.assertPKs(sq.where(f.year == 2003), [])

        self.assertPKs(sq.where(f.month == 1), [0])
        self.assertPKs(sq.where(f.month > 1), [1, 2])
        self.assertPKs(sq.where(f.month == 4), [])

        self.assertPKs(sq.where(f.day == 2), [0])
        self.assertPKs(sq.where(f.day > 2), [1, 2])
        self.assertPKs(sq.where(f.day == 5), [])

    def test_extract_time_where(self, f=None):
        if f is None:
            f = NullModel.time_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.hour == 3), [0])
        self.assertPKs(sq.where(f.hour == 4), [1, 2])
        self.assertPKs(sq.where(f.hour == 5), [])

        self.assertPKs(sq.where(f.minute == 4), [0])
        self.assertPKs(sq.where(f.minute > 4), [1, 2])
        self.assertPKs(sq.where(f.minute == 7), [])

        self.assertPKs(sq.where(f.second == 5), [0])
        self.assertPKs(sq.where(f.second > 5), [1, 2])
        self.assertPKs(sq.where(f.second == 8), [])


class UniqueTestCase(ModelTestCase):
    requires = [UniqueModel, MultiIndexModel]

    def test_unique(self):
        uniq1 = UniqueModel.create(name='a')
        uniq2 = UniqueModel.create(name='b')
        self.assertRaises(Exception, UniqueModel.create, name='a')
        test_db.rollback()

    def test_multi_index(self):
        mi1 = MultiIndexModel.create(f1='a', f2='a', f3='a')
        mi2 = MultiIndexModel.create(f1='b', f2='b', f3='b')
        self.assertRaises(Exception, MultiIndexModel.create, f1='a', f2='a', f3='b')
        test_db.rollback()
        self.assertRaises(Exception, MultiIndexModel.create, f1='b', f2='b', f3='a')
        test_db.rollback()

        mi3 = MultiIndexModel.create(f1='a', f2='b', f3='b')

class NonIntPKTestCase(ModelTestCase):
    requires = [NonIntModel, NonIntRelModel]

    def test_non_int_pk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        self.assertEqual(ni1.pk, 'a1')

        ni2 = NonIntModel(pk='a2', data='ni2')
        ni2.save(force_insert=True)
        self.assertEqual(ni2.pk, 'a2')

        ni2.save()
        self.assertEqual(ni2.pk, 'a2')

        self.assertEqual(NonIntModel.select().count(), 2)

        ni1_db = NonIntModel.get(NonIntModel.pk=='a1')
        self.assertEqual(ni1_db.data, ni1.data)

        self.assertEqual([(x.pk, x.data) for x in NonIntModel.select().order_by(NonIntModel.pk)], [
            ('a1', 'ni1'), ('a2', 'ni2'),
        ])

    def test_non_int_fk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        ni2 = NonIntModel.create(pk='a2', data='ni2')

        rni11 = NonIntRelModel(non_int_model=ni1)
        rni12 = NonIntRelModel(non_int_model=ni1)
        rni11.save()
        rni12.save()

        self.assertEqual([r.id for r in ni1.nr.order_by(NonIntRelModel.id)], [rni11.id, rni12.id])
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [])

        rni21 = NonIntRelModel.create(non_int_model=ni2)
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [rni21.id])

        sq = NonIntRelModel.select().join(NonIntModel).where(NonIntModel.data == 'ni2')
        self.assertEqual([r.id for r in sq], [rni21.id])


class PrimaryForeignKeyTestCase(ModelTestCase):
    requires = [Job, JobExecutionRecord]

    def test_primary_foreign_key(self):
        # we have one job, unexecuted, and therefore no executed jobs
        job = Job.create(name='Job One')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([], list(executed_jobs))

        # after execution, we must have one executed job
        exec_record = JobExecutionRecord.create(job=job, status='success')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([job], list(executed_jobs))

        # we must not be able to create another execution record for the job
        self.assertRaises(Exception, JobExecutionRecord.create, job=job, status='success')
        test_db.rollback()


class NonPKFKCreateTableTestCase(BasePeeweeTestCase):
    def test_create_table(self):
        class A(TestModel):
            cf = CharField(max_length=100, unique=True)
            df = DecimalField(
                max_digits=4,
                decimal_places=2,
                auto_round=True,
                unique=True)

        class CF(TestModel):
            a = ForeignKeyField(A, to_field='cf')

        class DF(TestModel):
            a = ForeignKeyField(A, to_field='df')

        cf_create, _ = compiler.create_table(CF)
        self.assertEqual(
            cf_create,
            'CREATE TABLE "cf" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" VARCHAR(100) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("cf"))')

        df_create, _ = compiler.create_table(DF)
        self.assertEqual(
            df_create,
            'CREATE TABLE "df" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" DECIMAL(4, 2) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("df"))')

class DeferredForeignKeyTestCase(ModelTestCase):
    requires = [Snippet, Language]

    def test_field_definitions(self):
        self.assertEqual(Snippet._meta.fields['language'].rel_model, Language)
        self.assertEqual(Language._meta.fields['selected_snippet'].rel_model,
                         Snippet)

    def test_create_table_query(self):
        query, params = compiler.create_table(Snippet)
        self.assertEqual(
            query,
            'CREATE TABLE "snippet" '
            '("id" INTEGER NOT NULL PRIMARY KEY, '
            '"code" TEXT NOT NULL, '
            '"language_id" INTEGER NOT NULL, '
            'FOREIGN KEY ("language_id") REFERENCES "language" ("id")'
            ')')

        query, params = compiler.create_table(Language)
        self.assertEqual(
            query,
            'CREATE TABLE "language" '
            '("id" INTEGER NOT NULL PRIMARY KEY, '
            '"name" VARCHAR(255) NOT NULL, '
            '"selected_snippet_id" INTEGER)')

    def test_storage_retrieval(self):
        python = Language.create(name='python')
        javascript = Language.create(name='javascript')
        p1 = Snippet.create(code="print 'Hello world'", language=python)
        p2 = Snippet.create(code="print 'Goodbye world'", language=python)
        j1 = Snippet.create(code="alert('Hello world')", language=javascript)

        self.assertEqual(Snippet.get(Snippet.id == p1.id).language, python)
        self.assertEqual(Snippet.get(Snippet.id == j1.id).language, javascript)

        python.selected_snippet = p2
        python.save()

        self.assertEqual(
            Language.get(Language.id == python.id).selected_snippet, p2)
        self.assertEqual(
            Language.get(Language.id == javascript.id).selected_snippet, None)


class DBColumnTestCase(ModelTestCase):
    requires = [DBUser, DBBlog]

    def test_select(self):
        sq = DBUser.select().where(DBUser.username == 'u1')
        self.assertSelect(sq, '"dbuser"."db_user_id", "dbuser"."db_username"', [])
        self.assertWhere(sq, '("dbuser"."db_username" = ?)', ['u1'])

        sq = DBUser.select(DBUser.user_id).join(DBBlog).where(DBBlog.title == 'b1')
        self.assertSelect(sq, '"dbuser"."db_user_id"', [])
        self.assertJoins(sq, ['INNER JOIN "dbblog" AS dbblog ON ("dbuser"."db_user_id" = "dbblog"."db_user")'])
        self.assertWhere(sq, '("dbblog"."db_title" = ?)', ['b1'])

    def test_db_column(self):
        u1 = DBUser.create(username='u1')
        u2 = DBUser.create(username='u2')
        u2_db = DBUser.get(DBUser.user_id==u2._get_pk_value())
        self.assertEqual(u2_db.username, 'u2')

        b1 = DBBlog.create(user=u1, title='b1')
        b2 = DBBlog.create(user=u2, title='b2')
        b2_db = DBBlog.get(DBBlog.blog_id==b2._get_pk_value())
        self.assertEqual(b2_db.user.user_id, u2.user_id)
        self.assertEqual(b2_db.title, 'b2')

        self.assertEqual([b.title for b in u2.dbblog_set], ['b2'])


class ConcurrencyTestCase(ModelTestCase):
    requires = [User]
    threads = 4

    def setUp(self):
        self._orig_db = test_db
        kwargs = {}
        try:  # Some engines need the extra kwargs.
            kwargs.update(test_db.connect_kwargs)
        except:
            pass
        if isinstance(test_db, SqliteDatabase):
            # Put a very large timeout in place to avoid `database is locked`
            # when using SQLite (default is 5).
            kwargs['timeout'] = 30

        User._meta.database = self.new_connection()
        super(ConcurrencyTestCase, self).setUp()

    def tearDown(self):
        User._meta.database = self._orig_db
        super(ConcurrencyTestCase, self).tearDown()

    def test_multiple_writers(self):
        def create_user_thread(low, hi):
            for i in range(low, hi):
                User.create(username='u%d' % i)
            User._meta.database.close()

        threads = []

        for i in range(self.threads):
            threads.append(threading.Thread(target=create_user_thread, args=(i*10, i * 10 + 10)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), self.threads * 10)

    def test_multiple_readers(self):
        data_queue = Queue()

        def reader_thread(q, num):
            for i in range(num):
                data_queue.put(User.select().count())

        threads = []

        for i in range(self.threads):
            threads.append(threading.Thread(target=reader_thread, args=(data_queue, 20)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(data_queue.qsize(), self.threads * 20)


class CompoundSelectTestCase(ModelTestCase):
    requires = [User, UniqueModel, OrderedModel]
    # User -> username, UniqueModel -> name, OrderedModel -> title
    test_values = {
        User.username: ['a', 'b', 'c', 'd'],
        UniqueModel.name: ['b', 'd', 'e'],
        OrderedModel.title: ['a', 'c', 'e'],
    }

    def setUp(self):
        super(CompoundSelectTestCase, self).setUp()
        for field, values in self.test_values.items():
            for value in values:
                field.model_class.create(**{field.name: value})

    def requires_op(op):
        def decorator(fn):
            @wraps(fn)
            def inner(self):
                if op in test_db.compound_operations:
                    return fn(self)
                elif TEST_VERBOSITY > 0:
                    print_('"%s" not supported, skipping %s' %
                           (op, fn.__name__))
            return inner
        return decorator

    def assertValues(self, query, expected):
        self.assertEqual(sorted(query.tuples()),
                         [(x,) for x in sorted(expected)])

    def assertPermutations(self, op, expected):
        fields = {
            User: User.username,
            UniqueModel: UniqueModel.name,
            OrderedModel: OrderedModel.title,
        }
        for key in itertools.permutations(fields.keys(), 2):
            if key in expected:
                left, right = key
                query = op(left.select(fields[left]).order_by(),
                           right.select(fields[right]).order_by())
                # Ensure the sorted tuples returned from the query are equal
                # to the sorted values we expected for this combination.
                self.assertValues(query, expected[key])

    @requires_op('UNION')
    def test_union(self):
        all_letters = ['a', 'b', 'c', 'd', 'e']
        self.assertPermutations(operator.or_, {
            (User, UniqueModel): all_letters,
            (User, OrderedModel): all_letters,
            (UniqueModel, User): all_letters,
            (UniqueModel, OrderedModel): all_letters,
            (OrderedModel, User): all_letters,
            (OrderedModel, UniqueModel): all_letters,
        })

    @requires_op('UNION')
    def test_union_from(self):
        uq = User.select(User.username).where(User.username << ['a', 'b', 'd'])
        oq = (OrderedModel
              .select(OrderedModel.title)
              .where(OrderedModel.title << ['a', 'b'])
              .order_by())
        iq = UniqueModel.select(UniqueModel.name)
        union = uq | oq | iq

        query = User.select(SQL('1')).from_(union)
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT 1 FROM ('
            'SELECT "users"."username" FROM "users" AS users '
            'WHERE ("users"."username" IN (?, ?, ?)) '
            'UNION '
            'SELECT "orderedmodel"."title" FROM "orderedmodel" AS orderedmodel'
            ' WHERE ("orderedmodel"."title" IN (?, ?)) '
            'UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel'
            ')'))
        self.assertEqual(params, ['a', 'b', 'd', 'a', 'b'])

    @requires_op('UNION')
    def test_union_count(self):
        a = User.select().where(User.username == 'a')
        c_and_d = User.select().where(User.username << ['c', 'd'])
        self.assertEqual(a.count(), 1)
        self.assertEqual(c_and_d.count(), 2)

        union = a | c_and_d
        self.assertEqual(union.wrapped_count(), 3)

        overlapping = User.select() | c_and_d
        self.assertEqual(overlapping.wrapped_count(), 4)

    @requires_op('INTERSECT')
    def test_intersect(self):
        self.assertPermutations(operator.and_, {
            (User, UniqueModel): ['b', 'd'],
            (User, OrderedModel): ['a', 'c'],
            (UniqueModel, User): ['b', 'd'],
            (UniqueModel, OrderedModel): ['e'],
            (OrderedModel, User): ['a', 'c'],
            (OrderedModel, UniqueModel): ['e'],
        })

    @requires_op('EXCEPT')
    def test_except(self):
        self.assertPermutations(operator.sub, {
            (User, UniqueModel): ['a', 'c'],
            (User, OrderedModel): ['b', 'd'],
            (UniqueModel, User): ['e'],
            (UniqueModel, OrderedModel): ['b', 'd'],
            (OrderedModel, User): ['e'],
            (OrderedModel, UniqueModel): ['a', 'c'],
        })

    @requires_op('INTERSECT')
    @requires_op('EXCEPT')
    def test_symmetric_difference(self):
        self.assertPermutations(operator.xor, {
            (User, UniqueModel): ['a', 'c', 'e'],
            (User, OrderedModel): ['b', 'd', 'e'],
            (UniqueModel, User): ['a', 'c', 'e'],
            (UniqueModel, OrderedModel): ['a', 'b', 'c', 'd'],
            (OrderedModel, User): ['b', 'd', 'e'],
            (OrderedModel, UniqueModel): ['a', 'b', 'c', 'd'],
        })

    def test_model_instances(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        query = union.order_by(SQL('username').desc()).limit(3)
        self.assertEqual([user.username for user in query],
                         ['e', 'd', 'c'])

    @requires_op('UNION')
    def test_union_sql(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        sql, params = compiler.generate_select(union)
        self.assertEqual(sql, (
            'SELECT "users"."username" FROM "users" AS users UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel'))

    @requires_op('UNION')
    def test_union_subquery(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        query = User.select().where(User.username << union)
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username" '
            'FROM "users" AS users WHERE ("users"."username" IN '
            '(SELECT "users"."username" FROM "users" AS users UNION '
            'SELECT "uniquemodel"."name" FROM "uniquemodel" AS uniquemodel))'))

    @requires_op('UNION')
    @requires_op('INTERSECT')
    def test_complex(self):
        left = User.select(User.username).where(User.username << ['a', 'b'])
        right = UniqueModel.select(UniqueModel.name).where(
            UniqueModel.name << ['b', 'd', 'e'])

        query = (left & right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [{'username': 'b'}])

        query = (left | right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [
            {'username': 'a'},
            {'username': 'b'},
            {'username': 'd'},
            {'username': 'e'}])

class ModelOptionInheritanceTestCase(BasePeeweeTestCase):
    def test_db_table(self):
        self.assertEqual(User._meta.db_table, 'users')

        class Foo(TestModel):
            pass
        self.assertEqual(Foo._meta.db_table, 'foo')

        class Foo2(TestModel):
            pass
        self.assertEqual(Foo2._meta.db_table, 'foo2')

        class Foo_3(TestModel):
            pass
        self.assertEqual(Foo_3._meta.db_table, 'foo_3')

    def test_custom_options(self):
        class A(Model):
            class Meta:
                a = 'a'

        class B1(A):
            class Meta:
                b = 1

        class B2(A):
            class Meta:
                b = 2

        self.assertEqual(A._meta.a, 'a')
        self.assertEqual(B1._meta.a, 'a')
        self.assertEqual(B2._meta.a, 'a')
        self.assertEqual(B1._meta.b, 1)
        self.assertEqual(B2._meta.b, 2)

    def test_option_inheritance(self):
        x_test_db = SqliteDatabase('testing.db')
        child2_db = SqliteDatabase('child2.db')

        class FakeUser(Model):
            pass

        class ParentModel(Model):
            title = CharField()
            user = ForeignKeyField(FakeUser)

            class Meta:
                database = x_test_db

        class ChildModel(ParentModel):
            pass

        class ChildModel2(ParentModel):
            special_field = CharField()

            class Meta:
                database = child2_db

        class GrandChildModel(ChildModel):
            pass

        class GrandChildModel2(ChildModel2):
            special_field = TextField()

        self.assertEqual(ParentModel._meta.database.database, 'testing.db')
        self.assertEqual(ParentModel._meta.model_class, ParentModel)

        self.assertEqual(ChildModel._meta.database.database, 'testing.db')
        self.assertEqual(ChildModel._meta.model_class, ChildModel)
        self.assertEqual(sorted(ChildModel._meta.fields.keys()), [
            'id', 'title', 'user'
        ])

        self.assertEqual(ChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(ChildModel2._meta.model_class, ChildModel2)
        self.assertEqual(sorted(ChildModel2._meta.fields.keys()), [
            'id', 'special_field', 'title', 'user'
        ])

        self.assertEqual(GrandChildModel._meta.database.database, 'testing.db')
        self.assertEqual(GrandChildModel._meta.model_class, GrandChildModel)
        self.assertEqual(sorted(GrandChildModel._meta.fields.keys()), [
            'id', 'title', 'user'
        ])

        self.assertEqual(GrandChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(GrandChildModel2._meta.model_class, GrandChildModel2)
        self.assertEqual(sorted(GrandChildModel2._meta.fields.keys()), [
            'id', 'special_field', 'title', 'user'
        ])
        self.assertTrue(isinstance(GrandChildModel2._meta.fields['special_field'], TextField))

    def test_order_by_inheritance(self):
        class Base(TestModel):
            created = DateTimeField()

            class Meta:
                order_by = ('-created',)

        class Foo(Base):
            data = CharField()

        class Bar(Base):
            val = IntegerField()
            class Meta:
                order_by = ('-val',)

        foo_order_by = Foo._meta.order_by[0]
        self.assertTrue(isinstance(foo_order_by, Field))
        self.assertTrue(foo_order_by.model_class is Foo)
        self.assertEqual(foo_order_by.name, 'created')

        bar_order_by = Bar._meta.order_by[0]
        self.assertTrue(isinstance(bar_order_by, Field))
        self.assertTrue(bar_order_by.model_class is Bar)
        self.assertEqual(bar_order_by.name, 'val')


class ModelInheritanceTestCase(ModelTestCase):
    requires = [Blog, BlogTwo, User]

    def test_model_inheritance_attrs(self):
        self.assertEqual(Blog._meta.get_field_names(), ['pk', 'user', 'title', 'content', 'pub_date'])
        self.assertEqual(BlogTwo._meta.get_field_names(), ['pk', 'user', 'content', 'pub_date', 'title', 'extra_field'])

        self.assertEqual(Blog._meta.primary_key.name, 'pk')
        self.assertEqual(BlogTwo._meta.primary_key.name, 'pk')

        self.assertEqual(Blog.user.related_name, 'blog_set')
        self.assertEqual(BlogTwo.user.related_name, 'blogtwo_set')

        self.assertEqual(User.blog_set.rel_model, Blog)
        self.assertEqual(User.blogtwo_set.rel_model, BlogTwo)

        self.assertFalse(BlogTwo._meta.db_table == Blog._meta.db_table)

    def test_model_inheritance_flow(self):
        u = User.create(username='u')

        b = Blog.create(title='b', user=u)
        b2 = BlogTwo.create(title='b2', extra_field='foo', user=u)

        self.assertEqual(list(u.blog_set), [b])
        self.assertEqual(list(u.blogtwo_set), [b2])

        self.assertEqual(Blog.select().count(), 1)
        self.assertEqual(BlogTwo.select().count(), 1)

        b_from_db = Blog.get(Blog.pk==b.pk)
        b2_from_db = BlogTwo.get(BlogTwo.pk==b2.pk)

        self.assertEqual(b_from_db.user, u)
        self.assertEqual(b2_from_db.user, u)
        self.assertEqual(b2_from_db.extra_field, 'foo')


class DatabaseTestCase(BasePeeweeTestCase):
    def test_deferred_database(self):
        deferred_db = SqliteDatabase(None)
        self.assertTrue(deferred_db.deferred)

        class DeferredModel(Model):
            class Meta:
                database = deferred_db

        self.assertRaises(Exception, deferred_db.connect)
        sq = DeferredModel.select()
        self.assertRaises(Exception, sq.execute)

        deferred_db.init(':memory:')
        self.assertFalse(deferred_db.deferred)

        # connecting works
        conn = deferred_db.connect()
        DeferredModel.create_table()
        sq = DeferredModel.select()
        self.assertEqual(list(sq), [])

        deferred_db.init(None)
        self.assertTrue(deferred_db.deferred)

    def test_sql_error(self):
        bad_sql = 'select asdf from -1;'
        self.assertRaises(Exception, query_db.execute_sql, bad_sql)
        self.assertEqual(query_db.last_error, (bad_sql, None))

class _SqliteDateTestHelper(BasePeeweeTestCase):
    datetimes = [
        datetime.datetime(2000, 1, 2, 3, 4, 5),
        datetime.datetime(2000, 2, 3, 4, 5, 6),
    ]

    def create_date_model(self, date_fn):
        dp_db = SqliteDatabase(':memory:')
        class SqDp(Model):
            datetime_field = DateTimeField()
            date_field = DateField()
            time_field = TimeField()
            null_datetime_field = DateTimeField(null=True)

            class Meta:
                database = dp_db

            @classmethod
            def date_query(cls, field, part):
                return (SqDp
                        .select(date_fn(field, part))
                        .tuples()
                        .order_by(SqDp.id))

        SqDp.create_table()

        for d in self.datetimes:
            SqDp.create(datetime_field=d, date_field=d.date(),
                        time_field=d.time())

        return SqDp

class SqliteDatePartTestCase(_SqliteDateTestHelper):
    def test_sqlite_date_part(self):
        date_fn = lambda field, part: fn.date_part(part, field)
        SqDp = self.create_date_model(date_fn)

        for part in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.datetime_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('year', 'month', 'day'):
            for i, dp in enumerate(SqDp.date_query(SqDp.date_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.time_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        # ensure that the where clause works
        query = SqDp.select().where(fn.date_part('year', SqDp.datetime_field) == 2000)
        self.assertEqual(query.count(), 2)

        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 1)
        self.assertEqual(query.count(), 1)
        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 3)
        self.assertEqual(query.count(), 0)

        null_sqdp = SqDp.create(
            datetime_field=datetime.datetime.now(),
            date_field=datetime.date.today(),
            time_field=datetime.time(0, 0),
            null_datetime_field=datetime.datetime(2014, 1, 1))
        query = SqDp.select().where(
            fn.date_part('year', SqDp.null_datetime_field) == 2014)
        self.assertEqual(query.count(), 1)
        self.assertEqual(list(query), [null_sqdp])


class SqliteDateTruncTestCase(_SqliteDateTestHelper):
    def test_sqlite_date_trunc(self):
        date_fn = lambda field, part: fn.date_trunc(part, field)
        SqDp = self.create_date_model(date_fn)

        def assertQuery(field, part, expected):
            values = SqDp.date_query(field, part)
            self.assertEqual([r[0] for r in values], expected)

        assertQuery(SqDp.datetime_field, 'year', ['2000', '2000'])
        assertQuery(SqDp.datetime_field, 'month', ['2000-01', '2000-02'])
        assertQuery(SqDp.datetime_field, 'day', ['2000-01-02', '2000-02-03'])
        assertQuery(SqDp.datetime_field, 'hour', [
            '2000-01-02 03', '2000-02-03 04'])
        assertQuery(SqDp.datetime_field, 'minute', [
            '2000-01-02 03:04', '2000-02-03 04:05'])
        assertQuery(SqDp.datetime_field, 'second', [
            '2000-01-02 03:04:05', '2000-02-03 04:05:06'])

        null_sqdp = SqDp.create(
            datetime_field=datetime.datetime.now(),
            date_field=datetime.date.today(),
            time_field=datetime.time(0, 0),
            null_datetime_field=datetime.datetime(2014, 1, 1))
        assertQuery(SqDp.null_datetime_field, 'year', [None, None, '2014'])


class CheckConstraintTestCase(ModelTestCase):
    requires = [CheckModel]

    def test_check_constraint(self):
        CheckModel.create(value=1)
        if isinstance(test_db, MySQLDatabase):
            # MySQL silently ignores all check constraints.
            CheckModel.create(value=0)
        else:
            with test_db.transaction() as txn:
                self.assertRaises(IntegrityError, CheckModel.create, value=0)
                txn.rollback()


class SQLAllTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(SQLAllTestCase, self).setUp()
        fake_db = SqliteDatabase(':memory:')
        UniqueModel._meta.database = fake_db
        SeqModelA._meta.database = fake_db
        MultiIndexModel._meta.database = fake_db

    def tearDown(self):
        super(SQLAllTestCase, self).tearDown()
        UniqueModel._meta.database = test_db
        SeqModelA._meta.database = test_db
        MultiIndexModel._meta.database = test_db

    def test_sqlall(self):
        sql = UniqueModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "uniquemodel" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"name" VARCHAR(255) NOT NULL)'),
            'CREATE UNIQUE INDEX "uniquemodel_name" ON "uniquemodel" ("name")',
        ])

        sql = MultiIndexModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "multiindexmodel" ("id" INTEGER NOT NULL PRIMARY '
             'KEY, "f1" VARCHAR(255) NOT NULL, "f2" VARCHAR(255) NOT NULL, '
             '"f3" VARCHAR(255) NOT NULL)'),
            ('CREATE UNIQUE INDEX "multiindexmodel_f1_f2" ON "multiindexmodel"'
             ' ("f1", "f2")'),
            ('CREATE INDEX "multiindexmodel_f2_f3" ON "multiindexmodel" '
             '("f2", "f3")'),
        ])

        sql = SeqModelA.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "seqmodela" ("id" INTEGER NOT NULL PRIMARY KEY '
             'DEFAULT NEXTVAL(\'just_testing_seq\'), "num" INTEGER NOT NULL)'),
        ])


class LongIndexTestCase(BasePeeweeTestCase):
    def test_long_index(self):
        class LongIndexModel(TestModel):
            a123456789012345678901234567890 = CharField()
            b123456789012345678901234567890 = CharField()
            c123456789012345678901234567890 = CharField()

        fields = LongIndexModel._meta.get_fields()[1:]
        self.assertEqual(len(fields), 3)

        sql, params = compiler.create_index(LongIndexModel, fields, False)
        self.assertEqual(sql, (
            'CREATE INDEX "longindexmodel_85c2f7db5319d3c0c124a1594087a1cb" '
            'ON "longindexmodel" ('
            '"a123456789012345678901234567890", '
            '"b123456789012345678901234567890", '
            '"c123456789012345678901234567890")'
        ))


class ConnectionStateTestCase(BasePeeweeTestCase):
    def test_connection_state(self):
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())
        test_db.close()
        self.assertTrue(test_db.is_closed())
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())


class TopologicalSortTestCase(unittest.TestCase):
    def test_topological_sort_fundamentals(self):
        FKF = ForeignKeyField
        # we will be topo-sorting the following models
        class A(Model): pass
        class B(Model): a = FKF(A)              # must follow A
        class C(Model): a, b = FKF(A), FKF(B)   # must follow A and B
        class D(Model): c = FKF(C)              # must follow A and B and C
        class E(Model): e = FKF('self')
        # but excluding this model, which is a child of E
        class Excluded(Model): e = FKF(E)

        # property 1: output ordering must not depend upon input order
        repeatable_ordering = None
        for input_ordering in permutations([A, B, C, D, E]):
            output_ordering = sort_models_topologically(input_ordering)
            repeatable_ordering = repeatable_ordering or output_ordering
            self.assertEqual(repeatable_ordering, output_ordering)

        # property 2: output ordering must have same models as input
        self.assertEqual(len(output_ordering), 5)
        self.assertFalse(Excluded in output_ordering)

        # property 3: parents must precede children
        def assert_precedes(X, Y):
            lhs, rhs = map(output_ordering.index, [X, Y])
            self.assertTrue(lhs < rhs)
        assert_precedes(A, B)
        assert_precedes(B, C)  # if true, C follows A by transitivity
        assert_precedes(C, D)  # if true, D follows A and B by transitivity

        # property 4: independent model hierarchies must be in name order
        assert_precedes(A, E)

class TestMetadataIntrospection(ModelTestCase):
    requires = [
        User, Blog, Comment, CompositeKeyModel, MultiIndexModel, UniqueModel,
        Category]

    def setUp(self):
        super(TestMetadataIntrospection, self).setUp()
        self.pk_index = database_class is not SqliteDatabase

    def test_get_tables(self):
        tables = test_db.get_tables()
        for model in self.requires:
            self.assertTrue(model._meta.db_table in tables)

        UniqueModel.drop_table()
        self.assertFalse(UniqueModel._meta.db_table in test_db.get_tables())

    def test_get_indexes(self):
        indexes = test_db.get_indexes(UniqueModel._meta.db_table)
        num_indexes = self.pk_index and 2 or 1
        self.assertEqual(len(indexes), num_indexes)

        idx, = [idx for idx in indexes if idx.name == 'uniquemodel_name']
        self.assertEqual(idx.columns, ['name'])
        self.assertTrue(idx.unique)

        indexes = dict(
            (idx.name, idx) for idx in
            test_db.get_indexes(MultiIndexModel._meta.db_table))
        num_indexes = self.pk_index and 3 or 2
        self.assertEqual(len(indexes), num_indexes)

        idx_f1f2 = indexes['multiindexmodel_f1_f2']
        self.assertEqual(sorted(idx_f1f2.columns), ['f1', 'f2'])
        self.assertTrue(idx_f1f2.unique)

        idx_f2f3 = indexes['multiindexmodel_f2_f3']
        self.assertEqual(sorted(idx_f2f3.columns), ['f2', 'f3'])
        self.assertFalse(idx_f2f3.unique)
        self.assertEqual(idx_f2f3.table, 'multiindexmodel')

        # SQLite *will* create an index here, so we will always have one.
        indexes = test_db.get_indexes(CompositeKeyModel._meta.db_table)
        self.assertEqual(len(indexes), 1)
        self.assertEqual(sorted(indexes[0].columns), ['f1', 'f2'])
        self.assertTrue(indexes[0].unique)

    def test_get_columns(self):
        def get_columns(model):
            return dict(
                (column.name, column)
                for column in test_db.get_columns(model._meta.db_table))

        def assertColumns(model, col_names, nullable, pks):
            columns = get_columns(model)
            self.assertEqual(sorted(columns), col_names)
            for column, metadata in columns.items():
                self.assertEqual(metadata.null, column in nullable)
                self.assertEqual(metadata.table, model._meta.db_table)
                self.assertEqual(metadata.primary_key, column in pks)

        assertColumns(User, ['id', 'username'], [], ['id'])
        assertColumns(
            Blog,
            ['content', 'pk', 'pub_date', 'title', 'user_id'],
            ['pub_date'],
            ['pk'])
        assertColumns(UniqueModel, ['id', 'name'], [], ['id'])
        assertColumns(MultiIndexModel, ['f1', 'f2', 'f3', 'id'], [], ['id'])
        assertColumns(
            CompositeKeyModel,
            ['f1', 'f2', 'f3'],
            [],
            ['f1', 'f2'])
        assertColumns(
            Category,
            ['id', 'name', 'parent_id'],
            ['parent_id'],
            ['id'])

    def test_get_primary_keys(self):
        def assertPKs(model_class, expected):
            self.assertEqual(
                test_db.get_primary_keys(model_class._meta.db_table),
                expected)

        assertPKs(User, ['id'])
        assertPKs(Blog, ['pk'])
        assertPKs(MultiIndexModel, ['id'])
        assertPKs(CompositeKeyModel, ['f1', 'f2'])
        assertPKs(UniqueModel, ['id'])
        assertPKs(Category, ['id'])

    def test_get_foreign_keys(self):
        def assertFKs(model_class, expected):
            foreign_keys = test_db.get_foreign_keys(model_class._meta.db_table)
            self.assertEqual(len(foreign_keys), len(expected))
            self.assertEqual(
                [(fk.column, fk.dest_table, fk.dest_column)
                 for fk in foreign_keys],
                expected)

        assertFKs(Category, [('parent_id', 'category', 'id')])
        assertFKs(User, [])
        assertFKs(Blog, [('user_id', 'users', 'id')])
        assertFKs(Comment, [('blog_id', 'blog', 'pk')])


def permutations(xs):
    if not xs:
        yield []
    else:
        for y, ys in selections(xs):
            for pys in permutations(ys):
                yield [y] + pys

def selections(xs):
    for i in range(len(xs)):
        yield (xs[i], xs[:i] + xs[i + 1:])


if test_db.for_update:
    class ForUpdateTestCase(ModelTestCase):
        requires = [User]

        def tearDown(self):
            test_db.set_autocommit(True)

        def test_for_update(self):
            u1 = self.create_user('u1')
            u2 = self.create_user('u2')
            u3 = self.create_user('u3')

            test_db.set_autocommit(False)

            # select a user for update
            users = User.select().where(User.username == 'u1').for_update()
            updated = User.update(username='u1_edited').where(User.username == 'u1').execute()
            self.assertEqual(updated, 1)

            # open up a new connection to the database
            new_db = self.new_connection()

            # select the username, it will not register as being updated
            res = new_db.execute_sql('select username from users where id = %s;' % u1.id)
            username = res.fetchone()[0]
            self.assertEqual(username, 'u1')

            # committing will cause the lock to be released
            test_db.commit()

            # now we get the update
            res = new_db.execute_sql('select username from users where id = %s;' % u1.id)
            username = res.fetchone()[0]
            self.assertEqual(username, 'u1_edited')


elif TEST_VERBOSITY > 0:
    print_('Skipping "for update" tests')

if test_db.for_update_nowait:
    class ForUpdateNoWaitTestCase(ModelTestCase):
        requires = [User]

        def tearDown(self):
            test_db.set_autocommit(True)

        def test_for_update_exc(self):
            u1 = self.create_user('u1')
            test_db.set_autocommit(False)

            user = (User
                    .select()
                    .where(User.username == 'u1')
                    .for_update(nowait=True)
                    .execute())

            # Open up a second conn.
            new_db = self.new_connection()

            class User2(User):
                class Meta:
                    database = new_db
                    db_table = User._meta.db_table

            # Select the username -- it will raise an error.
            def try_lock():
                user2 = (User2
                         .select()
                         .where(User2.username == 'u1')
                         .for_update(nowait=True)
                         .execute())
            self.assertRaises(OperationalError, try_lock)
            test_db.rollback()


elif TEST_VERBOSITY > 0:
    print_('Skipping "for update + nowait" tests')

if test_db.sequences:
    class SequenceTestCase(ModelTestCase):
        requires = [SeqModelA, SeqModelB]

        def test_sequence_shared(self):
            a1 = SeqModelA.create(num=1)
            a2 = SeqModelA.create(num=2)
            b1 = SeqModelB.create(other_num=101)
            b2 = SeqModelB.create(other_num=102)
            a3 = SeqModelA.create(num=3)

            self.assertEqual(a1.id, a2.id - 1)
            self.assertEqual(a2.id, b1.id - 1)
            self.assertEqual(b1.id, b2.id - 1)
            self.assertEqual(b2.id, a3.id - 1)

elif TEST_VERBOSITY > 0:
    print_('Skipping "sequence" tests')

if database_class is PostgresqlDatabase:
    class TestUnicodeConversion(ModelTestCase):
        requires = [User]

        def setUp(self):
            super(TestUnicodeConversion, self).setUp()

            # Create a user object with UTF-8 encoded username.
            ustr = ulit('Ísland')
            self.user = User.create(username=ustr)

        def tearDown(self):
            super(TestUnicodeConversion, self).tearDown()
            test_db.register_unicode = True
            test_db.close()

        def reset_encoding(self, encoding):
            test_db.close()
            conn = test_db.get_conn()
            conn.set_client_encoding(encoding)

        def test_unicode_conversion(self):
            # Per psycopg2's documentation, in Python2, strings are returned as
            # 8-bit str objects encoded in the client encoding. In python3,
            # the strings are automatically decoded in the connection encoding.

            # Turn off unicode conversion on a per-connection basis.
            test_db.register_unicode = False
            self.reset_encoding('LATIN1')

            u = User.get(User.id == self.user.id)
            if sys.version_info[0] < 3:
                self.assertFalse(u.username == self.user.username)
            else:
                self.assertTrue(u.username == self.user.username)

            test_db.register_unicode = True
            self.reset_encoding('LATIN1')

            u = User.get(User.id == self.user.id)
            self.assertEqual(u.username, self.user.username)

    class TestPostgresqlSchema(ModelTestCase):
        requires = [PGSchema]

        def setUp(self):
            test_db.execute_sql('CREATE SCHEMA huey;')
            super(TestPostgresqlSchema,self).setUp()

        def tearDown(self):
            super(TestPostgresqlSchema,self).tearDown()
            test_db.execute_sql('DROP SCHEMA huey;')

        def test_pg_schema(self):
            pgs = PGSchema.create(data='huey')
            pgs_db = PGSchema.get(PGSchema.data == 'huey')
            self.assertEqual(pgs.id, pgs_db.id)


if test_db.foreign_keys:
    class ForeignKeyConstraintTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_constraint_exists(self):
            # IntegrityError is raised when we specify a non-existent user_id.
            max_id = User.select(fn.Max(User.id)).scalar() or 0

            def will_fail():
                with test_db.transaction() as txn:
                    Blog.create(user=max_id + 1, title='testing')

            self.assertRaises(IntegrityError, will_fail)

        def test_constraint_creation(self):
            class FKC_a(TestModel):
                name = CharField()

            fkc_proxy = Proxy()

            class FKC_b(TestModel):
                fkc_a = ForeignKeyField(fkc_proxy)

            fkc_proxy.initialize(FKC_a)

            with test_db.transaction() as txn:
                FKC_b.drop_table(True)
                FKC_a.drop_table(True)
                FKC_a.create_table()
                FKC_b.create_table()

                # Foreign key constraint is not enforced.
                fb = FKC_b.create(fkc_a=-1000)
                fb.delete_instance()

                # Add constraint.
                test_db.create_foreign_key(FKC_b, FKC_b.fkc_a)

                def _trigger_exc():
                    with test_db.savepoint() as s1:
                        fb = FKC_b.create(fkc_a=-1000)

                self.assertRaises(IntegrityError, _trigger_exc)

                fa = FKC_a.create(name='fa')
                fb = FKC_b.create(fkc_a=fa)
                txn.rollback()


elif TEST_VERBOSITY > 0:
    print_('Skipping "foreign key" tests')

if test_db.drop_cascade:
    class DropCascadeTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_drop_cascade(self):
            u1 = User.create(username='u1')
            b1 = Blog.create(user=u1, title='b1')

            User.drop_table(cascade=True)
            self.assertFalse(User.table_exists())

            # The constraint is dropped, we can create a blog for a non-
            # existant user.
            Blog.create(user=-1, title='b2')


elif TEST_VERBOSITY > 0:
    print_('Skipping "drop/cascade" tests')


if test_db.window_functions:
    class WindowFunctionTestCase(ModelTestCase):
        """Use int_field & float_field to test window queries."""
        requires = [NullModel]
        data = (
            # int / float -- we'll use int for grouping.
            (1, 10),
            (1, 20),
            (2, 1),
            (2, 3),
            (3, 100),
        )

        def setUp(self):
            super(WindowFunctionTestCase, self).setUp()
            for int_v, float_v in self.data:
                NullModel.create(int_field=int_v, float_field=float_v)

        def test_partition_unordered(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(
                             partition_by=[NullModel.int_field]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0),
                (1, 20.0, 15.0),
                (2, 1.0, 2.0),
                (2, 3.0, 2.0),
                (3, 100.0, 100.0),
            ])

        def test_named_window(self):
            window = Window(partition_by=[NullModel.int_field])
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(window))
                     .window(window)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0),
                (1, 20.0, 15.0),
                (2, 1.0, 2.0),
                (2, 3.0, 2.0),
                (3, 100.0, 100.0),
            ])

            window = Window(
                partition_by=[NullModel.int_field],
                order_by=[NullModel.float_field.desc()])
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(window=window))
                     .window(window)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 2),
                (1, 20.0, 1),
                (2, 1.0, 2),
                (2, 3.0, 1),
                (3, 100.0, 1),
            ])

        def test_multi_window(self):
            w1 = Window(partition_by=[NullModel.int_field]).alias('w1')
            w2 = Window(order_by=[NullModel.int_field]).alias('w2')
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(window=w1),
                         fn.Rank().over(window=w2))
                     .window(w1, w2)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0, 1),
                (1, 20.0, 15.0, 1),
                (2, 1.0, 2.0, 3),
                (2, 3.0, 2.0, 3),
                (3, 100.0, 100.0, 5),
            ])

        def test_ordered_unpartitioned(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(
                             order_by=[NullModel.float_field]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 3),
                (1, 20.0, 4),
                (2, 1.0, 1),
                (2, 3.0, 2),
                (3, 100.0, 5),
            ])

        def test_ordered_partitioned(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(
                             partition_by=[NullModel.int_field],
                             order_by=[NullModel.float_field.desc()]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 2),
                (1, 20.0, 1),
                (2, 1.0, 2),
                (2, 3.0, 1),
                (3, 100.0, 1),
            ])

        def test_empty_over(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.lag(NullModel.int_field, 1).over())
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, None),
                (1, 20.0, 1),
                (2, 1.0, 1),
                (2, 3.0, 2),
                (3, 100.0, 2),
            ])

        def test_docs_example(self):
            NullModel.delete().execute()  # Clear out the table.

            curr_dt = datetime.datetime(2014, 1, 1)
            one_day = datetime.timedelta(days=1)
            for i in range(3):
                for j in range(i + 1):
                    NullModel.create(int_field=i, datetime_field=curr_dt)
                curr_dt += one_day

            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.datetime_field,
                         fn.Count(NullModel.id).over(
                             partition_by=[fn.date_trunc(
                                 'day', NullModel.datetime_field)]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (0, datetime.datetime(2014, 1, 1), 1),
                (1, datetime.datetime(2014, 1, 2), 2),
                (1, datetime.datetime(2014, 1, 2), 2),
                (2, datetime.datetime(2014, 1, 3), 3),
                (2, datetime.datetime(2014, 1, 3), 3),
                (2, datetime.datetime(2014, 1, 3), 3),
            ])


elif TEST_VERBOSITY > 0:
    print_('Skipping "window function" tests')

if test_db.distinct_on:
    class DistinctOnTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_distinct_on(self):
            for i in range(1, 4):
                u = User.create(username='u%s' % i)
                for j in range(i):
                    Blog.create(user=u, title='b-%s-%s' % (i, j))

            query = (Blog
                     .select(User.username, Blog.title)
                     .join(User)
                     .order_by(User.username, Blog.title)
                     .distinct([User.username])
                     .tuples())
            self.assertEqual(list(query), [
                ('u1', 'b-1-0'),
                ('u2', 'b-2-0'),
                ('u3', 'b-3-0')])

            query = (Blog
                     .select(
                         fn.Distinct(User.username),
                         User.username,
                         Blog.title)
                     .join(User)
                     .order_by(Blog.title)
                     .tuples())
            self.assertEqual(list(query), [
                ('u1', 'u1', 'b-1-0'),
                ('u2', 'u2', 'b-2-0'),
                ('u2', 'u2', 'b-2-1'),
                ('u3', 'u3', 'b-3-0'),
                ('u3', 'u3', 'b-3-1'),
                ('u3', 'u3', 'b-3-2'),
            ])

elif TEST_VERBOSITY > 0:
    print_('Skipping "distinct on" tests')


if isinstance(test_db, SqliteDatabase):
    class TestOuterLoopInnerCommit(ModelTestCase):
        requires = [User, Blog]

        def tearDown(self):
            test_db.set_autocommit(True)
            super(TestOuterLoopInnerCommit, self).tearDown()

        def test_outer_loop_inner_commit(self):
            # By default we are in autocommit mode (isolation_level=None).
            self.assertEqual(test_db.get_conn().isolation_level, None)

            for username in ['u1', 'u2', 'u3']:
                User.create(username=username)

            for user in User.select():
                Blog.create(user=user, title='b-%s' % user.username)

            # These statements are auto-committed.
            new_db = self.new_connection()
            count = new_db.execute_sql('select count(*) from blog;').fetchone()
            self.assertEqual(count[0], 3)

            self.assertEqual(Blog.select().count(), 3)
            blog_titles = [b.title for b in Blog.select().order_by(Blog.title)]
            self.assertEqual(blog_titles, ['b-u1', 'b-u2', 'b-u3'])

            self.assertEqual(Blog.delete().execute(), 3)

            # If we disable autocommit, we need to explicitly call begin().
            test_db.set_autocommit(False)
            test_db.begin()

            for user in User.select():
                Blog.create(user=user, title='b-%s' % user.username)

            # These statements have not been committed.
            new_db = self.new_connection()
            count = new_db.execute_sql('select count(*) from blog;').fetchone()
            self.assertEqual(count[0], 0)

            self.assertEqual(Blog.select().count(), 3)
            blog_titles = [b.title for b in Blog.select().order_by(Blog.title)]
            self.assertEqual(blog_titles, ['b-u1', 'b-u2', 'b-u3'])

            test_db.commit()
            count = new_db.execute_sql('select count(*) from blog;').fetchone()
            self.assertEqual(count[0], 3)


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
