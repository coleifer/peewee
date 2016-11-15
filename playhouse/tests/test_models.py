# encoding=utf-8

import sys
from functools import partial

from peewee import *
from peewee import ModelOptions
from peewee import sqlite3
from playhouse.tests.base import compiler
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import normal_compiler
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if
from playhouse.tests.base import skip_unless
from playhouse.tests.base import test_db
from playhouse.tests.base import ulit
from playhouse.tests.models import *


in_memory_db = database_initializer.get_in_memory_database()
supports_tuples = sqlite3.sqlite_version_info >= (3, 15, 0)

class GCModel(Model):
    name = CharField(unique=True)
    key = CharField()
    value = CharField()
    number = IntegerField(default=0)

    class Meta:
        database = in_memory_db
        indexes = (
            (('key', 'value'), True),
        )

def incrementer():
    d = {'value': 0}
    def increment():
        d['value'] += 1
        return d['value']
    return increment

class DefaultsModel(Model):
    field = IntegerField(default=incrementer())
    control = IntegerField(default=1)

    class Meta:
        database = in_memory_db


class TestQueryingModels(ModelTestCase):
    requires = [User, Blog]

    def setUp(self):
        super(TestQueryingModels, self).setUp()
        self._orig_db_insert_many = test_db.insert_many

    def tearDown(self):
        super(TestQueryingModels, self).tearDown()
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

    def test_select_with_bind_to(self):
        self.create_users_blogs(1, 1)
        blog = Blog.select(
            Blog,
            User,
            (User.username == 'u0').alias('is_u0').bind_to(User),
            (User.username == 'u1').alias('is_u1').bind_to(User)
        ).join(User).get()

        self.assertTrue(blog.user.is_u0)
        self.assertFalse(blog.user.is_u1)

    def test_scalar(self):
        User.create_users(5)

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

    def test_noop_query(self):
        query = User.noop()
        with self.assertQueryCount(1) as qc:
            result = [row for row in query]

        self.assertEqual(result, [])

    def test_update(self):
        User.create_users(5)
        uq = User.update(username='u-edited').where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u1', 'u2', 'u3', 'u4', 'u5'])

        uq.execute()
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u-edited', 'u-edited', 'u-edited', 'u4', 'u5'])

        self.assertRaises(KeyError, User.update, doesnotexist='invalid')

    def test_update_subquery(self):
        User.create_users(3)
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

        self.assertRaises(KeyError, lambda: User.insert(doesnotexist='invalid'))

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

    def test_insert_many_validates_fields_by_default(self):
        self.assertTrue(User.insert_many([])._validate_fields)

    def test_insert_many_without_field_validation(self):
        self.assertFalse(User.insert_many([], validate_fields=False)._validate_fields)

    def test_delete(self):
        User.create_users(5)
        dq = User.delete().where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual(User.select().count(), 5)
        nr = dq.execute()
        self.assertEqual(nr, 3)
        self.assertEqual([u.username for u in User.select()], ['u4', 'u5'])

    def test_raw(self):
        User.create_users(3)
        interpolation = test_db.interpolation

        with self.assertQueryCount(1):
            query = 'select * from users where username IN (%s, %s)' % (
                interpolation, interpolation)
            rq = User.raw(query, 'u1', 'u3')
            self.assertEqual([u.username for u in rq], ['u1', 'u3'])

            # iterate again
            self.assertEqual([u.username for u in rq], ['u1', 'u3'])

        query = ('select id, username, %s as secret '
                 'from users where username = %s')
        rq = User.raw(
            query % (interpolation, interpolation),
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
            User.create(username='u%d' % i)
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

    def test_model_iter(self):
        self.create_users_blogs(3, 2)
        usernames = [user.username for user in User]
        self.assertEqual(sorted(usernames), ['u0', 'u1', 'u2'])

        blogs = list(Blog)
        self.assertEqual(len(blogs), 6)


class TestInsertEmptyModel(ModelTestCase):
    requires = [EmptyModel, NoPKModel]

    def test_insert_empty(self):
        query = EmptyModel.insert()
        sql, params = compiler.generate_insert(query)
        if isinstance(test_db, MySQLDatabase):
            self.assertEqual(sql, (
                'INSERT INTO "emptymodel" ("emptymodel"."id") '
                'VALUES (DEFAULT)'))
        else:
            self.assertEqual(sql, 'INSERT INTO "emptymodel" DEFAULT VALUES')
        self.assertEqual(params, [])

        # Verify the query works.
        pk = query.execute()
        em = EmptyModel.get(EmptyModel.id == pk)

        # Verify we can also use `create()`.
        em2 = EmptyModel.create()
        self.assertEqual(EmptyModel.select().count(), 2)

    def test_no_pk(self):
        obj = NoPKModel.create(data='1')
        self.assertEqual(NoPKModel.select(fn.COUNT('1')).scalar(), 1)

        res = (NoPKModel
               .update(data='1-e')
               .where(NoPKModel.data == '1')
               .execute())
        self.assertEqual(res, 1)
        self.assertEqual(NoPKModel.select(fn.COUNT('1')).scalar(), 1)

        NoPKModel(data='2').save()
        NoPKModel(data='3').save()
        self.assertEqual(
            [obj.data for obj in NoPKModel.select().order_by(NoPKModel.data)],
            ['1-e', '2', '3'])


class TestModelAPIs(ModelTestCase):
    requires = [User, Blog, Category, UserCategory, UniqueMultiField,
                NonIntModel]

    def setUp(self):
        super(TestModelAPIs, self).setUp()
        GCModel.drop_table(True)
        GCModel.create_table()

    def test_related_name(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
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

    def test_callable_related_name(self):
        class Foo(TestModel):
            pass

        def rel_name(field):
            return '%s_%s_ref' % (field.model_class._meta.name, field.name)

        class Bar(TestModel):
            fk1 = ForeignKeyField(Foo, related_name=rel_name)
            fk2 = ForeignKeyField(Foo, related_name=rel_name)

        class Baz(Bar):
            pass

        self.assertTrue(Foo.bar_fk1_ref.rel_model is Bar)
        self.assertTrue(Foo.bar_fk2_ref.rel_model is Bar)
        self.assertTrue(Foo.baz_fk1_ref.rel_model is Baz)
        self.assertTrue(Foo.baz_fk2_ref.rel_model is Baz)
        self.assertFalse(hasattr(Foo, 'bar_set'))
        self.assertFalse(hasattr(Foo, 'baz_set'))

    def test_fk_exceptions(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(parent=c1, name='c2')
        self.assertEqual(c1.parent, None)
        self.assertEqual(c2.parent, c1)

        c2_db = Category.get(Category.id == c2.id)
        self.assertEqual(c2_db.parent, c1)

        u = User.create(username='u1')
        b = Blog.create(user=u, title='b')
        b2 = Blog(title='b2')

        self.assertEqual(b.user, u)
        self.assertRaises(User.DoesNotExist, getattr, b2, 'user')

    def test_fk_cache_invalidated(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
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

    def test_fk_object_id(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2')
        c2.parent_id = c1.id
        c2.save()
        self.assertEqual(c2.parent, c1)
        c2_db = Category.get(Category.name == 'c2')
        self.assertEqual(c2_db.parent, c1)

    def test_fk_caching(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2', parent=c1)
        c2_db = Category.get(Category.id == c2.id)

        with self.assertQueryCount(1):
            parent = c2_db.parent
            self.assertEqual(parent, c1)

            parent = c2_db.parent

    def test_related_id(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        for u in [u1, u2]:
            for j in range(2):
                Blog.create(user=u, title='%s-%s' % (u.username, j))

        with self.assertQueryCount(1):
            query = Blog.select().order_by(Blog.pk)
            user_ids = [blog.user_id for blog in query]

        self.assertEqual(user_ids, [u1.id, u1.id, u2.id, u2.id])

        p1 = Category.create(name='p1')
        p2 = Category.create(name='p2')
        c1 = Category.create(name='c1', parent=p1)
        c2 = Category.create(name='c2', parent=p2)

        with self.assertQueryCount(1):
            query = Category.select().order_by(Category.id)
            self.assertEqual(
                [cat.parent_id for cat in query],
                [None, None, p1.id, p2.id])

    def test_fk_object_id(self):
        u = User.create(username='u')
        b = Blog.create(user_id=u.id, title='b1')
        self.assertEqual(b._data['user'], u.id)
        self.assertFalse('user' in b._obj_cache)

        with self.assertQueryCount(1):
            u_db = b.user
            self.assertEqual(u_db.id, u.id)

        b_db = Blog.get(Blog.pk == b.pk)
        with self.assertQueryCount(0):
            self.assertEqual(b_db.user_id, u.id)

        u2 = User.create(username='u2')
        Blog.create(user=u, title='b1x')
        Blog.create(user=u2, title='b2')

        q = Blog.select().where(Blog.user_id == u2.id)
        self.assertEqual(q.count(), 1)
        self.assertEqual(q.get().title, 'b2')

        q = Blog.select(Blog.pk, Blog.user_id).where(Blog.user_id == u.id)
        self.assertEqual(q.count(), 2)
        result = q.order_by(Blog.pk).first()
        self.assertEqual(result.user_id, u.id)
        with self.assertQueryCount(1):
            self.assertEqual(result.user.id, u.id)

    def test_object_id_descriptor_naming(self):
        class Person(Model):
            pass

        class Foo(Model):
            me = ForeignKeyField(Person, db_column='me', related_name='foo1')
            another = ForeignKeyField(Person, db_column='_whatever_',
                                      related_name='foo2')
            another2 = ForeignKeyField(Person, db_column='person_id',
                                       related_name='foo3')
            plain = ForeignKeyField(Person, related_name='foo4')

        self.assertTrue(Foo.me is Foo.me_id)
        self.assertTrue(Foo.another is Foo._whatever_)
        self.assertTrue(Foo.another2 is Foo.person_id)
        self.assertTrue(Foo.plain is Foo.plain_id)

        self.assertRaises(AttributeError, lambda: Foo.another_id)
        self.assertRaises(AttributeError, lambda: Foo.another2_id)

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
        User.create_users(10)
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

    def test_save_fk(self):
        blog = Blog(title='b1', content='')
        blog.user = User(username='u1')
        blog.user.save()
        with self.assertQueryCount(1):
            blog.save()

        with self.assertQueryCount(1):
            blog_db = (Blog
                       .select(Blog, User)
                       .join(User)
                       .where(Blog.pk == blog.pk)
                       .get())
            self.assertEqual(blog_db.user.username, 'u1')

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

    def test_save_dirty_auto(self):
        User._meta.only_save_dirty = True
        Blog._meta.only_save_dirty = True
        try:
            with self.log_queries() as query_logger:
                u = User.create(username='u1')
                b = Blog.create(title='b1', user=u)

            # The default value for the blog content will be saved as well.
            self.assertEqual(
                [params for _, params in query_logger.queries],
                [['u1'], [u.id, 'b1', '']])

            with self.assertQueryCount(0):
                self.assertTrue(u.save() is False)
                self.assertTrue(b.save() is False)

            u.username = 'u1-edited'
            b.title = 'b1-edited'
            with self.assertQueryCount(1):
                with self.log_queries() as query_logger:
                    self.assertEqual(u.save(), 1)

            sql, params = query_logger.queries[0]
            self.assertTrue(sql.startswith('UPDATE'))
            self.assertEqual(params, ['u1-edited', u.id])

            with self.assertQueryCount(1):
                with self.log_queries() as query_logger:
                    self.assertEqual(b.save(), 1)

            sql, params = query_logger.queries[0]
            self.assertTrue(sql.startswith('UPDATE'))
            self.assertEqual(params, ['b1-edited', b.pk])
        finally:
            User._meta.only_save_dirty = False
            Blog._meta.only_save_dirty = False

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
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        self.assertEqual(u1, User.get(username='u1'))
        self.assertEqual(u2, User.get(username='u2'))
        self.assertFalse(u1 == u2)

        self.assertEqual(u1, User.get(User.username == 'u1'))
        self.assertEqual(u2, User.get(User.username == 'u2'))

    def test_get_exception(self):
        exc = None
        try:
            User.get(User.id == 0)
        except Exception as raised_exc:
            exc = raised_exc
        else:
            assert False

        self.assertEqual(exc.__module__, 'playhouse.tests.models')
        self.assertEqual(
            str(type(exc)),
            "<class 'playhouse.tests.models.UserDoesNotExist'>")
        if sys.version_info[0] < 3:
            self.assertTrue(exc.message.startswith('Instance matching query'))
            self.assertTrue(exc.message.endswith('PARAMS: [0]'))

    def test_get_or_create(self):
        u1, created = User.get_or_create(username='u1')
        self.assertTrue(created)

        u1_x, created = User.get_or_create(username='u1')
        self.assertFalse(created)

        self.assertEqual(u1.id, u1_x.id)
        self.assertEqual(User.select().count(), 1)

    def test_get_or_create_extended(self):
        gc1, created = GCModel.get_or_create(
            name='huey',
            key='k1',
            value='v1',
            defaults={'number': 3})
        self.assertTrue(created)
        self.assertEqual(gc1.name, 'huey')
        self.assertEqual(gc1.key, 'k1')
        self.assertEqual(gc1.value, 'v1')
        self.assertEqual(gc1.number, 3)

        gc1_db, created = GCModel.get_or_create(
            name='huey',
            defaults={'key': 'k2', 'value': 'v2'})
        self.assertFalse(created)
        self.assertEqual(gc1_db.id, gc1.id)
        self.assertEqual(gc1_db.key, 'k1')

        def integrity_error():
            gc2, created = GCModel.get_or_create(
                name='huey',
                key='kx',
                value='vx')

        self.assertRaises(IntegrityError, integrity_error)

        gc2, created = GCModel.get_or_create(
            name__ilike='%nugget%',
            defaults={
                'name': 'foo-nugget',
                'key': 'k2',
                'value': 'v2'})
        self.assertTrue(created)
        self.assertEqual(gc2.name, 'foo-nugget')

        gc2_db, created = GCModel.get_or_create(
            name__ilike='%nugg%',
            defaults={'name': 'xx'})
        self.assertFalse(created)
        self.assertEqual(gc2_db.id, gc2.id)

        self.assertEqual(GCModel.select().count(), 2)

    def test_create_or_get(self):
        assertQC = partial(self.assertQueryCount, ignore_txn=True)

        with assertQC(1):
            user, new = User.create_or_get(username='charlie')

        self.assertTrue(user.id is not None)
        self.assertTrue(new)

        with assertQC(2):
            user_get, new = User.create_or_get(username='peewee', id=user.id)

        self.assertFalse(new)
        self.assertEqual(user_get.id, user.id)
        self.assertEqual(user_get.username, 'charlie')
        self.assertEqual(User.select().count(), 1)

        # Test with a unique model.
        with assertQC(1):
            um, new = UniqueMultiField.create_or_get(
                name='baby huey',
                field_a='fielda',
                field_b=1)

        self.assertTrue(new)
        self.assertEqual(um.name, 'baby huey')
        self.assertEqual(um.field_a, 'fielda')
        self.assertEqual(um.field_b, 1)

        with assertQC(2):
            um_get, new = UniqueMultiField.create_or_get(
                name='baby huey',
                field_a='fielda-modified',
                field_b=2)

        self.assertFalse(new)
        self.assertEqual(um_get.id, um.id)
        self.assertEqual(um_get.name, um.name)
        self.assertEqual(um_get.field_a, um.field_a)
        self.assertEqual(um_get.field_b, um.field_b)
        self.assertEqual(UniqueMultiField.select().count(), 1)

        # Test with a non-integer primary key model.
        with assertQC(1):
            nm, new = NonIntModel.create_or_get(
                pk='1337',
                data='sweet mickey')

        self.assertTrue(new)
        self.assertEqual(nm.pk, '1337')
        self.assertEqual(nm.data, 'sweet mickey')

        with assertQC(2):
            nm_get, new = NonIntModel.create_or_get(
                pk='1337',
                data='michael-nuggie')

        self.assertFalse(new)
        self.assertEqual(nm_get.pk, nm.pk)
        self.assertEqual(nm_get.data, nm.data)
        self.assertEqual(NonIntModel.select().count(), 1)

    def test_peek(self):
        users = User.create_users(3)

        with self.assertQueryCount(1):
            sq = User.select().order_by(User.username)

            # call it once
            u1 = sq.peek()
            self.assertEqual(u1.username, 'u1')

            # check the result cache
            self.assertEqual(len(sq._qr._result_cache), 1)

            # call it again and we get the same result, but not an
            # extra query
            self.assertEqual(sq.peek().username, 'u1')

        with self.assertQueryCount(0):
            # no limit is applied.
            usernames = [u.username for u in sq]
            self.assertEqual(usernames, ['u1', 'u2', 'u3'])

    def test_first(self):
        users = User.create_users(3)

        with self.assertQueryCount(1):
            sq = User.select().order_by(User.username)

            # call it once
            first = sq.first()
            self.assertEqual(first.username, 'u1')

            # check the result cache
            self.assertEqual(len(sq._qr._result_cache), 1)

            # call it again and we get the same result, but not an
            # extra query
            self.assertEqual(sq.first().username, 'u1')

        with self.assertQueryCount(0):
            # also note that a limit has been applied.
            all_results = [obj for obj in sq]
            self.assertEqual(all_results, [first])

            usernames = [u.username for u in sq]
            self.assertEqual(usernames, ['u1'])

        with self.assertQueryCount(0):
            # call first() after iterating
            self.assertEqual(sq.first().username, 'u1')

            usernames = [u.username for u in sq]
            self.assertEqual(usernames, ['u1'])

        # call it with an empty result
        sq = User.select().where(User.username == 'not-here')
        self.assertEqual(sq.first(), None)

    def test_deleting(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

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
            User.create(username='u%d' % i)

        with test_db.transaction():
            for user in User.select():
                for i in range(20):
                    Blog.create(user=user, title='b-%d-%d' % (user.id, i))

        count = Blog.select().count()
        self.assertEqual(count, 200)

    def test_exists(self):
        u1 = User.create(username='u1')
        self.assertTrue(User.select().where(User.username == 'u1').exists())
        self.assertFalse(User.select().where(User.username == 'u2').exists())

    def test_unicode(self):
        # create a unicode literal
        ustr = ulit('Lýðveldið Ísland')
        u = User.create(username=ustr)

        # query using the unicode literal
        u_db = User.get(User.username == ustr)

        # the db returns a unicode literal
        self.assertEqual(u_db.username, ustr)

        # delete the user
        self.assertEqual(u.delete_instance(), 1)

        # convert the unicode to a utf8 string
        utf8_str = ustr.encode('utf-8')

        # create using the utf8 string
        u2 = User.create(username=utf8_str)

        # query using unicode literal
        u2_db = User.get(User.username == ustr)

        # we get unicode back
        self.assertEqual(u2_db.username, ustr)

    def test_unicode_issue202(self):
        ustr = ulit('M\u00f6rk')
        user = User.create(username=ustr)
        self.assertEqual(user.username, ustr)

    def test_on_conflict(self):
        gc = GCModel.create(name='g1', key='k1', value='v1')
        query = GCModel.insert(
            name='g1',
            key='k2',
            value='v2')
        self.assertRaises(IntegrityError, query.execute)

        # Ensure that we can ignore errors.
        res = query.on_conflict('IGNORE').execute()
        self.assertEqual(res, gc.id)
        self.assertEqual(GCModel.select().count(), 1)

        # Error ignored, no changes.
        gc_db = GCModel.get()
        self.assertEqual(gc_db.name, 'g1')
        self.assertEqual(gc_db.key, 'k1')
        self.assertEqual(gc_db.value, 'v1')

        # Replace the old, conflicting row, with the new data.
        res = query.on_conflict('REPLACE').execute()
        self.assertNotEqual(res, gc.id)
        self.assertEqual(GCModel.select().count(), 1)

        gc_db = GCModel.get()
        self.assertEqual(gc_db.name, 'g1')
        self.assertEqual(gc_db.key, 'k2')
        self.assertEqual(gc_db.value, 'v2')

        # Replaces also can occur when violating multi-column indexes.
        query = GCModel.insert(
            name='g2',
            key='k2',
            value='v2').on_conflict('REPLACE')

        res = query.execute()
        self.assertNotEqual(res, gc_db.id)
        self.assertEqual(GCModel.select().count(), 1)

        gc_db = GCModel.get()
        self.assertEqual(gc_db.name, 'g2')
        self.assertEqual(gc_db.key, 'k2')
        self.assertEqual(gc_db.value, 'v2')

    def test_on_conflict_many(self):
        if not SqliteDatabase.insert_many:
            return

        for i in range(5):
            key = 'gc%s' % i
            GCModel.create(name=key, key=key, value=key)

        insert = [
            {'name': key, 'key': 'x-%s' % key, 'value': key}
            for key in ['gc%s' % i for i in range(10)]]
        res = GCModel.insert_many(insert).on_conflict('IGNORE').execute()
        self.assertEqual(GCModel.select().count(), 10)

        gcs = list(GCModel.select().order_by(GCModel.id))
        first_five, last_five = gcs[:5], gcs[5:]

        # The first five should all be "gcI", the last five will have
        # "x-gcI" for their keys.
        self.assertEqual(
            [gc.key for gc in first_five],
            ['gc0', 'gc1', 'gc2', 'gc3', 'gc4'])

        self.assertEqual(
            [gc.key for gc in last_five],
            ['x-gc5', 'x-gc6', 'x-gc7', 'x-gc8', 'x-gc9'])

    def test_meta_get_field_index(self):
        index = Blog._meta.get_field_index(Blog.content)
        self.assertEqual(index, 3)

    def test_meta_remove_field(self):

        class _Model(Model):
            title = CharField(max_length=25)
            content = TextField(default='')

        _Model._meta.remove_field('content')
        self.assertTrue('content' not in _Model._meta.fields)
        self.assertTrue('content' not in _Model._meta.sorted_field_names)
        self.assertEqual([f.name for f in _Model._meta.sorted_fields],
                         ['id', 'title'])

    def test_meta_rel_for_model(self):
        class User(Model):
            pass
        class Category(Model):
            parent = ForeignKeyField('self')
        class Tweet(Model):
            user = ForeignKeyField(User)
        class Relationship(Model):
            from_user = ForeignKeyField(User, related_name='r1')
            to_user = ForeignKeyField(User, related_name='r2')

        UM = User._meta
        CM = Category._meta
        TM = Tweet._meta
        RM = Relationship._meta

        # Simple refs work.
        self.assertIsNone(UM.rel_for_model(Tweet))
        self.assertEqual(UM.rel_for_model(Tweet, multi=True), [])
        self.assertEqual(UM.reverse_rel_for_model(Tweet), Tweet.user)
        self.assertEqual(UM.reverse_rel_for_model(Tweet, multi=True),
                         [Tweet.user])

        # Multi fks.
        self.assertEqual(RM.rel_for_model(User), Relationship.from_user)
        self.assertEqual(RM.rel_for_model(User, multi=True),
                         [Relationship.from_user, Relationship.to_user])

        self.assertEqual(UM.reverse_rel_for_model(Relationship),
                         Relationship.from_user)
        self.assertEqual(UM.reverse_rel_for_model(Relationship, multi=True),
                         [Relationship.from_user, Relationship.to_user])

        # Self-refs work.
        self.assertEqual(CM.rel_for_model(Category), Category.parent)
        self.assertEqual(CM.reverse_rel_for_model(Category), Category.parent)

        # Field aliases work.
        UA = User.alias()
        self.assertEqual(TM.rel_for_model(UA), Tweet.user)


class TestAggregatesWithModels(ModelTestCase):
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


class TestMultiTableFromClause(ModelTestCase):
    requires = [Blog, Comment, User]

    def setUp(self):
        super(TestMultiTableFromClause, self).setUp()

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

class TestDeleteRecursive(ModelTestCase):
    requires = [
        Parent, Child, ChildNullableData, ChildPet, Orphan, OrphanPet, Package,
        PackageItem]

    def setUp(self):
        super(TestDeleteRecursive, self).setUp()
        self.p1 = p1 = Parent.create(data='p1')
        self.p2 = p2 = Parent.create(data='p2')
        c11 = Child.create(parent=p1)
        c12 = Child.create(parent=p1)
        c21 = Child.create(parent=p2)
        c22 = Child.create(parent=p2)
        o11 = Orphan.create(parent=p1)
        o12 = Orphan.create(parent=p1)
        o21 = Orphan.create(parent=p2)
        o22 = Orphan.create(parent=p2)

        for child in [c11, c12, c21, c22]:
            ChildPet.create(child=child)

        for orphan in [o11, o12, o21, o22]:
            OrphanPet.create(orphan=orphan)

        for i, child in enumerate([c11, c12]):
            for j in range(2):
                ChildNullableData.create(
                    child=child,
                    data='%s-%s' % (i, j))

    def test_recursive_delete_parent_sql(self):
        with self.log_queries() as query_logger:
            with self.assertQueryCount(5):
                self.p1.delete_instance(recursive=True, delete_nullable=False)

        queries = query_logger.queries
        update_cnd = ('UPDATE `childnullabledata` '
                      'SET `child_id` = %% '
                      'WHERE ('
                      '`childnullabledata`.`child_id` IN ('
                      'SELECT `t2`.`id` FROM `child` AS t2 WHERE ('
                      '`t2`.`parent_id` = %%)))')
        delete_cp = ('DELETE FROM `childpet` WHERE ('
                     '`child_id` IN ('
                     'SELECT `t1`.`id` FROM `child` AS t1 WHERE ('
                     '`t1`.`parent_id` = %%)))')
        delete_c = 'DELETE FROM `child` WHERE (`parent_id` = %%)'
        update_o = ('UPDATE `orphan` SET `parent_id` = %% WHERE ('
                    '`orphan`.`parent_id` = %%)')
        delete_p = 'DELETE FROM `parent` WHERE (`id` = %%)'
        sql_params = [
            (update_cnd, [None, self.p1.id]),
            (delete_cp, [self.p1.id]),
            (delete_c, [self.p1.id]),
            (update_o, [None, self.p1.id]),
            (delete_p, [self.p1.id]),
        ]
        self.assertQueriesEqual(queries, sql_params)

    def test_recursive_delete_child_queries(self):
        c2 = self.p1.child_set.order_by(Child.id.desc()).get()
        with self.log_queries() as query_logger:
            with self.assertQueryCount(3):
                c2.delete_instance(recursive=True, delete_nullable=False)

        queries = query_logger.queries

        update_cnd = ('UPDATE `childnullabledata` SET `child_id` = %% WHERE ('
                      '`childnullabledata`.`child_id` = %%)')
        delete_cp = 'DELETE FROM `childpet` WHERE (`child_id` = %%)'
        delete_c = 'DELETE FROM `child` WHERE (`id` = %%)'

        sql_params = [
            (update_cnd, [None, c2.id]),
            (delete_cp, [c2.id]),
            (delete_c, [c2.id]),
        ]
        self.assertQueriesEqual(queries, sql_params)

    def assertQueriesEqual(self, queries, expected):
        queries.sort()
        expected.sort()
        for i in range(len(queries)):
            sql, params = queries[i]
            expected_sql, expected_params = expected[i]
            expected_sql = (expected_sql
                            .replace('`', test_db.quote_char)
                            .replace('%%', test_db.interpolation))
            self.assertEqual(sql, expected_sql)
            self.assertEqual(params, expected_params)

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


@skip_if(lambda: isinstance(test_db, MySQLDatabase))
class TestTruncate(ModelTestCase):
    requires = [User]

    def test_truncate(self):
        for i in range(3):
            User.create(username='u%s' % i)

        User.truncate_table(restart_identity=True)
        self.assertEqual(User.select().count(), 0)

        u = User.create(username='ux')
        self.assertEqual(u.id, 1)


class TestManyToMany(ModelTestCase):
    requires = [User, Category, UserCategory]

    def setUp(self):
        super(TestManyToMany, self).setUp()
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

        cats = Category.select().join(UserCategory, JOIN.LEFT_OUTER).join(User, JOIN.LEFT_OUTER).where(
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


class TestCustomModelOptionsBase(PeeweeTestCase):
    def test_custom_model_options_base(self):
        db = SqliteDatabase(None)

        class DatabaseDescriptor(object):
            def __init__(self, db):
                self._db = db

            def __get__(self, instance_type, instance):
                if instance is not None:
                    return self._db
                return self

            def __set__(self, instance, value):
                pass

        class TestModelOptions(ModelOptions):
            database = DatabaseDescriptor(db)

        class BaseModel(Model):
            class Meta:
                model_options_base = TestModelOptions

        class TestModel(BaseModel):
            pass

        class TestChildModel(TestModel):
            pass

        self.assertEqual(id(TestModel._meta.database), id(db))
        self.assertEqual(id(TestChildModel._meta.database), id(db))


class TestModelOptionInheritance(PeeweeTestCase):
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

    def test_table_name_function(self):
        class Base(TestModel):
            class Meta:
                def db_table_func(model):
                    return model.__name__.lower() + 's'

        class User(Base):
            pass

        class SuperUser(User):
            class Meta:
                db_table = 'nugget'

        class MegaUser(SuperUser):
            class Meta:
                def db_table_func(model):
                    return 'mega'

        class Bear(Base):
            pass

        self.assertEqual(User._meta.db_table, 'users')
        self.assertEqual(Bear._meta.db_table, 'bears')
        self.assertEqual(SuperUser._meta.db_table, 'nugget')
        self.assertEqual(MegaUser._meta.db_table, 'mega')


class TestModelInheritance(ModelTestCase):
    requires = [Blog, BlogTwo, User]

    def test_model_inheritance_attrs(self):
        self.assertEqual(Blog._meta.sorted_field_names, ['pk', 'user', 'title', 'content', 'pub_date'])
        self.assertEqual(BlogTwo._meta.sorted_field_names, ['pk', 'user', 'content', 'pub_date', 'title', 'extra_field'])

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

    def test_inheritance_primary_keys(self):
        self.assertFalse(hasattr(Model, 'id'))

        class M1(Model): pass
        self.assertTrue(hasattr(M1, 'id'))

        class M2(Model):
            key = CharField(primary_key=True)
        self.assertFalse(hasattr(M2, 'id'))

        class M3(Model):
            id = TextField()
            key = IntegerField(primary_key=True)
        self.assertTrue(hasattr(M3, 'id'))
        self.assertFalse(M3.id.primary_key)

        class C1(M1): pass
        self.assertTrue(hasattr(C1, 'id'))
        self.assertTrue(C1.id.model_class is C1)

        class C2(M2): pass
        self.assertFalse(hasattr(C2, 'id'))
        self.assertTrue(C2.key.primary_key)
        self.assertTrue(C2.key.model_class is C2)

        class C3(M3): pass
        self.assertTrue(hasattr(C3, 'id'))
        self.assertFalse(C3.id.primary_key)
        self.assertTrue(C3.id.model_class is C3)


class TestAliasBehavior(ModelTestCase):
    requires = [UpperModel]

    def test_alias_with_coerce(self):
        UpperModel.create(data='test')
        um = UpperModel.get()
        self.assertEqual(um.data, 'TEST')

        Alias = UpperModel.alias()
        normal = (UpperModel.data == 'foo')
        aliased = (Alias.data == 'foo')
        _, normal_p = compiler.parse_node(normal)
        _, aliased_p = compiler.parse_node(aliased)
        self.assertEqual(normal_p, ['FOO'])
        self.assertEqual(aliased_p, ['FOO'])

        expected = (
            'SELECT "uppermodel"."id", "uppermodel"."data" '
            'FROM "uppermodel" AS uppermodel '
            'WHERE ("uppermodel"."data" = ?)')

        query = UpperModel.select().where(UpperModel.data == 'foo')
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, expected)
        self.assertEqual(params, ['FOO'])

        query = Alias.select().where(Alias.data == 'foo')
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, expected)
        self.assertEqual(params, ['FOO'])


@skip_unless(lambda: isinstance(test_db, PostgresqlDatabase))
class TestInsertReturningModelAPI(PeeweeTestCase):
    def setUp(self):
        super(TestInsertReturningModelAPI, self).setUp()

        self.db = database_initializer.get_database(
            'postgres',
            PostgresqlDatabase)

        class BaseModel(TestModel):
            class Meta:
                database = self.db

        self.BaseModel = BaseModel
        self.models = []

    def tearDown(self):
        if self.models:
            self.db.drop_tables(self.models, True)
        super(TestInsertReturningModelAPI, self).tearDown()

    def test_insert_returning(self):
        class User(self.BaseModel):
            username = CharField()
            class Meta:
                db_table = 'users'

        self.models.append(User)
        User.create_table()

        query = User.insert(username='charlie')
        sql, params = query.sql()
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") VALUES (%s) RETURNING "id"'))
        self.assertEqual(params, ['charlie'])

        result = query.execute()
        charlie = User.get(User.username == 'charlie')
        self.assertEqual(result, charlie.id)

        result2 = User.insert(username='huey').execute()
        self.assertTrue(result2 > result)
        huey = User.get(User.username == 'huey')
        self.assertEqual(result2, huey.id)

        mickey = User.create(username='mickey')
        self.assertEqual(mickey.id, huey.id + 1)
        mickey.save()
        self.assertEqual(User.select().count(), 3)

    def test_non_int_pk(self):
        class User(self.BaseModel):
            username = CharField(primary_key=True)
            data = IntegerField()
            class Meta:
                db_table = 'users'

        self.models.append(User)
        User.create_table()

        query = User.insert(username='charlie', data=1337)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username", "data") '
            'VALUES (%s, %s) RETURNING "username"'))
        self.assertEqual(params, ['charlie', 1337])

        self.assertEqual(query.execute(), 'charlie')
        charlie = User.get(User.data == 1337)
        self.assertEqual(charlie.username, 'charlie')

        huey = User.create(username='huey', data=1024)
        self.assertEqual(huey.username, 'huey')
        self.assertEqual(huey.data, 1024)

        huey_db = User.get(User.data == 1024)
        self.assertEqual(huey_db.username, 'huey')
        huey_db.save()
        self.assertEqual(huey_db.username, 'huey')

        self.assertEqual(User.select().count(), 2)

    def test_composite_key(self):
        class Person(self.BaseModel):
            first = CharField()
            last = CharField()
            data = IntegerField()

            class Meta:
                primary_key = CompositeKey('first', 'last')

        self.models.append(Person)
        Person.create_table()

        query = Person.insert(first='huey', last='leifer', data=3)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'INSERT INTO "person" ("first", "last", "data") '
            'VALUES (%s, %s, %s) RETURNING "first", "last"'))
        self.assertEqual(params, ['huey', 'leifer', 3])

        res = query.execute()
        self.assertEqual(res, ['huey', 'leifer'])

        huey = Person.get(Person.data == 3)
        self.assertEqual(huey.first, 'huey')
        self.assertEqual(huey.last, 'leifer')

        zaizee = Person.create(first='zaizee', last='owen', data=2)
        self.assertEqual(zaizee.first, 'zaizee')
        self.assertEqual(zaizee.last, 'owen')

        z_db = Person.get(Person.data == 2)
        self.assertEqual(z_db.first, 'zaizee')
        self.assertEqual(z_db.last, 'owen')
        z_db.save()

        self.assertEqual(Person.select().count(), 2)

    def test_insert_many(self):
        class User(self.BaseModel):
            username = CharField()
            class Meta:
                db_table = 'users'

        self.models.append(User)
        User.create_table()

        usernames = ['charlie', 'huey', 'zaizee']
        data = [{'username': username} for username in usernames]

        query = User.insert_many(data)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'VALUES (%s), (%s), (%s)'))
        self.assertEqual(params, usernames)

        res = query.execute()
        self.assertTrue(res is True)
        self.assertEqual(User.select().count(), 3)
        z = User.select().order_by(-User.username).get()
        self.assertEqual(z.username, 'zaizee')

        usernames = ['foo', 'bar', 'baz']
        data = [{'username': username} for username in usernames]
        query = User.insert_many(data).return_id_list()
        sql, params = query.sql()
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'VALUES (%s), (%s), (%s) RETURNING "id"'))
        self.assertEqual(params, usernames)

        res = list(query.execute())
        self.assertEqual(len(res), 3)
        foo = User.get(User.username == 'foo')
        bar = User.get(User.username == 'bar')
        baz = User.get(User.username == 'baz')
        self.assertEqual(res, [foo.id, bar.id, baz.id])


@skip_unless(lambda: isinstance(test_db, PostgresqlDatabase))
class TestReturningClause(ModelTestCase):
    requires = [User]

    def test_update_returning(self):
        User.create_users(3)
        u1, u2, u3 = [user for user in User.select().order_by(User.id)]

        uq = User.update(username='uII').where(User.id == u2.id)
        res = uq.execute()
        self.assertEqual(res, 1)  # Number of rows modified.

        uq = uq.returning(User.username)
        users = [user for user in uq.execute()]
        self.assertEqual(len(users), 1)
        user, = users
        self.assertEqual(user.username, 'uII')
        self.assertIsNone(user.id)  # Was not explicitly selected.

        uq = (User
              .update(username='huey')
              .where(User.username != 'uII')
              .returning(User))
        users = [user for user in uq.execute()]
        self.assertEqual(len(users), 2)
        self.assertTrue(all([user.username == 'huey' for user in users]))
        self.assertTrue(all([user.id is not None for user in users]))

        uq = uq.dicts().returning(User.username)
        user_data = [data for data in uq.execute()]
        self.assertEqual(
            user_data,
            [{'username': 'huey'}, {'username': 'huey'}])

    def test_delete_returning(self):
        User.create_users(10)

        dq = User.delete().where(User.username << ['u9', 'u10'])
        res = dq.execute()
        self.assertEqual(res, 2)  # Number of rows modified.

        dq = (User
              .delete()
              .where(User.username << ['u7', 'u8'])
              .returning(User.username))
        users = [user for user in dq.execute()]
        self.assertEqual(len(users), 2)

        usernames = sorted([user.username for user in users])
        self.assertEqual(usernames, ['u7', 'u8'])

        ids = [user.id for user in users]
        self.assertEqual(ids, [None, None])  # Was not selected.

        dq = (User
              .delete()
              .where(User.username == 'u1')
              .returning(User))
        users = [user for user in dq.execute()]
        self.assertEqual(len(users), 1)
        user, = users
        self.assertEqual(user.username, 'u1')
        self.assertIsNotNone(user.id)

    def test_insert_returning(self):
        iq = User.insert(username='zaizee').returning(User)
        users = [user for user in iq.execute()]
        self.assertEqual(len(users), 1)
        user, = users
        self.assertEqual(user.username, 'zaizee')
        self.assertIsNotNone(user.id)

        iq = (User
              .insert_many([
                  {'username': 'charlie'},
                  {'username': 'huey'},
                  {'username': 'connor'},
                  {'username': 'leslie'},
                  {'username': 'mickey'}])
              .returning(User))
        users = sorted([user for user in iq.tuples().execute()])

        usernames = [username for _, username in users]
        self.assertEqual(usernames, [
            'charlie',
            'huey',
            'connor',
            'leslie',
            'mickey',
        ])

        id_charlie = users[0][0]
        id_mickey = users[-1][0]
        self.assertEqual(id_mickey - id_charlie, 4)


class TestModelHash(PeeweeTestCase):
    def test_hash(self):
        class MyUser(User):
            pass

        d = {}
        u1 = User(id=1)
        u2 = User(id=2)
        u3 = User(id=3)
        m1 = MyUser(id=1)
        m2 = MyUser(id=2)
        m3 = MyUser(id=3)

        d[u1] = 'u1'
        d[u2] = 'u2'
        d[m1] = 'm1'
        d[m2] = 'm2'
        self.assertTrue(u1 in d)
        self.assertTrue(u2 in d)
        self.assertFalse(u3 in d)
        self.assertTrue(m1 in d)
        self.assertTrue(m2 in d)
        self.assertFalse(m3 in d)

        self.assertEqual(d[u1], 'u1')
        self.assertEqual(d[u2], 'u2')
        self.assertEqual(d[m1], 'm1')
        self.assertEqual(d[m2], 'm2')

        un = User()
        mn = MyUser()
        d[un] = 'un'
        d[mn] = 'mn'
        self.assertTrue(un in d)  # Hash implementation.
        self.assertTrue(mn in d)
        self.assertEqual(d[un], 'un')
        self.assertEqual(d[mn], 'mn')


class TestDeleteNullableForeignKeys(ModelTestCase):
    requires = [User, Note, Flag, NoteFlagNullable]

    def test_delete(self):
        u = User.create(username='u')
        n = Note.create(user=u, text='n')
        f = Flag.create(label='f')
        nf1 = NoteFlagNullable.create(note=n, flag=f)
        nf2 = NoteFlagNullable.create(note=n, flag=None)
        nf3 = NoteFlagNullable.create(note=None, flag=f)
        nf4 = NoteFlagNullable.create(note=None, flag=None)

        self.assertEqual(nf1.delete_instance(), 1)
        self.assertEqual(nf2.delete_instance(), 1)
        self.assertEqual(nf3.delete_instance(), 1)
        self.assertEqual(nf4.delete_instance(), 1)


class TestJoinNullableForeignKey(ModelTestCase):
    requires = [Parent, Orphan, Child]

    def setUp(self):
        super(TestJoinNullableForeignKey, self).setUp()

        p1 = Parent.create(data='p1')
        p2 = Parent.create(data='p2')
        for i in range(1, 3):
            Child.create(parent=p1, data='child%s-p1' % i)
            Child.create(parent=p2, data='child%s-p2' % i)
            Orphan.create(parent=p1, data='orphan%s-p1' % i)

        Orphan.create(data='orphan1-noparent')
        Orphan.create(data='orphan2-noparent')

    def test_no_empty_instances(self):
        with self.assertQueryCount(1):
            query = (Orphan
                     .select(Orphan, Parent)
                     .join(Parent, JOIN.LEFT_OUTER)
                     .order_by(Orphan.id))
            res = [(orphan.data, orphan.parent is None) for orphan in query]

        self.assertEqual(res, [
            ('orphan1-p1', False),
            ('orphan2-p1', False),
            ('orphan1-noparent', True),
            ('orphan2-noparent', True),
        ])

    def test_unselected_fk_pk(self):
        with self.assertQueryCount(1):
            query = (Orphan
                     .select(Orphan.data, Parent.data)
                     .join(Parent, JOIN.LEFT_OUTER)
                     .order_by(Orphan.id))
            res = [(orphan.data, orphan.parent is None) for orphan in query]

        self.assertEqual(res, [
            ('orphan1-p1', False),
            ('orphan2-p1', False),
            ('orphan1-noparent', False),
            ('orphan2-noparent', False),
        ])

    def test_non_null_fk_unselected_fk(self):
        with self.assertQueryCount(1):
            query = (Child
                     .select(Child.data, Parent.data)
                     .join(Parent, JOIN.LEFT_OUTER)
                     .order_by(Child.id))
            res = [(child.data, child.parent is None) for child in query]

        self.assertEqual(res, [
            ('child1-p1', False),
            ('child1-p2', False),
            ('child2-p1', False),
            ('child2-p2', False),
        ])

        res = [child.parent.data for child in query]
        self.assertEqual(res, ['p1', 'p2', 'p1', 'p2'])

        res = [(child._data['parent'], child.parent.id) for child in query]
        self.assertEqual(res, [
            (None, None),
            (None, None),
            (None, None),
            (None, None),
        ])


class TestDefaultDirtyBehavior(PeeweeTestCase):
    def setUp(self):
        super(TestDefaultDirtyBehavior, self).setUp()
        DefaultsModel.drop_table(True)
        DefaultsModel.create_table()

    def test_default_dirty(self):
        DM = DefaultsModel
        DM._meta.only_save_dirty = True

        dm = DM()
        dm.save()

        self.assertEqual(dm.field, 1)
        self.assertEqual(dm.control, 1)

        dm_db = DM.get((DM.field == 1) & (DM.control == 1))
        self.assertEqual(dm_db.field, 1)
        self.assertEqual(dm_db.control, 1)

        # No changes.
        self.assertFalse(dm_db.save())

        dm2 = DM.create()
        self.assertEqual(dm2.field, 3)  # One extra when fetched from DB.
        self.assertEqual(dm2.control, 1)

        dm._meta.only_save_dirty = False

        dm3 = DM()
        self.assertEqual(dm3.field, 4)
        self.assertEqual(dm3.control, 1)
        dm3.save()

        dm3_db = DM.get(DM.id == dm3.id)
        self.assertEqual(dm3_db.field, 4)


class TestFunctionCoerceRegression(PeeweeTestCase):
    def test_function_coerce(self):
        class M1(Model):
            data = IntegerField()
            class Meta:
                database = in_memory_db

        class M2(Model):
            id = IntegerField()
            class Meta:
                database = in_memory_db

        in_memory_db.create_tables([M1, M2])

        for i in range(3):
            M1.create(data=i)
            M2.create(id=i + 1)

        qm1 = M1.select(fn.GROUP_CONCAT(M1.data).coerce(False).alias('data'))
        qm2 = M2.select(fn.GROUP_CONCAT(M2.id).coerce(False).alias('ids'))

        m1 = qm1.get()
        self.assertEqual(m1.data, '0,1,2')

        m2 = qm2.get()
        self.assertEqual(m2.ids, '1,2,3')


@skip_unless(
    lambda: (isinstance(test_db, PostgresqlDatabase) or
             (isinstance(test_db, SqliteDatabase) and supports_tuples)))
class TestTupleComparison(ModelTestCase):
    requires = [User]

    def test_tuples(self):
        ua = User.create(username='user-a')
        ub = User.create(username='user-b')
        uc = User.create(username='user-c')
        query = User.select().where(
            Tuple(User.username, User.id) == ('user-b', ub.id))
        self.assertEqual(query.count(), 1)
        obj = query.get()
        self.assertEqual(obj, ub)
