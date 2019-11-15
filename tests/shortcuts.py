import operator

from peewee import *
from playhouse.shortcuts import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_mysql
from .base_models import Category


class User(TestModel):
    username = TextField()

    @property
    def name_hash(self):
        return sum(map(ord, self.username)) % 10

class Tweet(TestModel):
    user = ForeignKeyField(User, backref='tweets')
    content = TextField()

class Tag(TestModel):
    tag = TextField()

class TweetTag(TestModel):
    tweet = ForeignKeyField(Tweet)
    tag = ForeignKeyField(Tag)

    class Meta:
        primary_key = CompositeKey('tweet', 'tag')

class Owner(TestModel):
    name = TextField()

class Label(TestModel):
    label = TextField()

class Gallery(TestModel):
    name = TextField()
    labels = ManyToManyField(Label, backref='galleries')
    owner = ForeignKeyField(Owner, backref='galleries')

GalleryLabel = Gallery.labels.through_model

class Student(TestModel):
    name = TextField()

StudentCourseProxy = DeferredThroughModel()

class Course(TestModel):
    name = TextField()
    students = ManyToManyField(Student, through_model=StudentCourseProxy,
                               backref='courses')

class StudentCourse(TestModel):
    student = ForeignKeyField(Student)
    course = ForeignKeyField(Course)

StudentCourseProxy.set_model(StudentCourse)

class Host(TestModel):
    name = TextField()

class Service(TestModel):
    host = ForeignKeyField(Host, backref='services')
    name = TextField()

class Device(TestModel):
    host = ForeignKeyField(Host, backref='+')
    name = TextField()

class Basket(TestModel):
    id = IntegerField(primary_key=True)

class Item(TestModel):
    id = IntegerField(primary_key=True)
    basket = ForeignKeyField(Basket)


class TestModelToDict(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Tweet, Tag, TweetTag]

    def setUp(self):
        super(TestModelToDict, self).setUp()
        self.user = User.create(username='peewee')

    def test_simple(self):
        with self.assertQueryCount(0):
            self.assertEqual(model_to_dict(self.user), {
                'id': self.user.id,
                'username': 'peewee'})

    def test_simple_recurse(self):
        tweet = Tweet.create(user=self.user, content='t1')
        with self.assertQueryCount(0):
            self.assertEqual(model_to_dict(tweet), {
                'id': tweet.id,
                'content': tweet.content,
                'user': {
                    'id': self.user.id,
                    'username': 'peewee'}})

        with self.assertQueryCount(0):
            self.assertEqual(model_to_dict(tweet, recurse=False), {
                'id': tweet.id,
                'content': tweet.content,
                'user': self.user.id})

    def test_simple_backref(self):
        with self.assertQueryCount(1):
            self.assertEqual(model_to_dict(self.user, backrefs=True), {
                'id': self.user.id,
                'tweets': [],
                'username': 'peewee'})

        tweet = Tweet.create(user=self.user, content='t0')

        # Two queries, one for tweets, one for tweet-tags.
        with self.assertQueryCount(2):
            self.assertEqual(model_to_dict(self.user, backrefs=True), {
                'id': self.user.id,
                'username': 'peewee',
                'tweets': [{'id': tweet.id, 'content': 't0',
                            'tweettag_set': []}]})

    def test_recurse_and_backrefs(self):
        tweet = Tweet.create(user=self.user, content='t0')
        with self.assertQueryCount(1):
            self.assertEqual(model_to_dict(tweet, backrefs=True), {
                'id': tweet.id,
                'content': 't0',
                'tweettag_set': [],
                'user': {'id': self.user.id, 'username': 'peewee'}})

    @requires_models(Category)
    def test_recursive_fk(self):
        root = Category.create(name='root')
        child = Category.create(name='child', parent=root)
        grandchild = Category.create(name='grandchild', parent=child)

        with self.assertQueryCount(0):
            for recurse in (True, False):
                self.assertEqual(model_to_dict(root, recurse=recurse), {
                    'name': 'root',
                    'parent': None})

        with self.assertQueryCount(1):
            self.assertEqual(model_to_dict(root, backrefs=True), {
                'name': 'root',
                'parent': None,
                'children': [{'name': 'child'}]})

        with self.assertQueryCount(1):
            self.assertEqual(model_to_dict(root, backrefs=True), {
                'name': 'root',
                'parent': None,
                'children': [{'name': 'child'}]})

        with self.assertQueryCount(1):
            self.assertEqual(model_to_dict(child, backrefs=True), {
                'name': 'child',
                'parent': {'name': 'root'},
                'children': [{'name': 'grandchild'}]})

        with self.assertQueryCount(0):
            self.assertEqual(model_to_dict(child, backrefs=False), {
                'name': 'child',
                'parent': {'name': 'root'}})

    def test_manytomany(self):
        tweet = Tweet.create(user=self.user, content='t0')
        tag1 = Tag.create(tag='t1')
        tag2 = Tag.create(tag='t2')
        Tag.create(tag='tx')
        TweetTag.create(tweet=tweet, tag=tag1)
        TweetTag.create(tweet=tweet, tag=tag2)

        with self.assertQueryCount(4):
            self.assertEqual(model_to_dict(self.user, backrefs=True), {
                'id': self.user.id,
                'username': 'peewee',
                'tweets': [{
                    'id': tweet.id,
                    'content': 't0',
                    'tweettag_set': [
                        {'tag': {'id': tag1.id, 'tag': 't1'}},
                        {'tag': {'id': tag2.id, 'tag': 't2'}}]}]})

    @requires_models(Label, Gallery, GalleryLabel, Owner)
    def test_manytomany_field(self):
        data = (
            ('charlie', 'family', ('nuggie', 'bearbe')),
            ('charlie', 'pets', ('huey', 'zaizee', 'beanie')),
            ('peewee', 'misc', ('nuggie', 'huey')))
        for owner_name, gallery, labels in data:
            owner, _ = Owner.get_or_create(name=owner_name)
            gallery = Gallery.create(name=gallery, owner=owner)
            label_objects = [Label.get_or_create(label=l)[0] for l in labels]
            gallery.labels.add(label_objects)

        query = (Gallery
                 .select(Gallery, Owner)
                 .join(Owner)
                 .switch(Gallery)
                 .join(GalleryLabel)
                 .join(Label)
                 .where(Label.label == 'nuggie')
                 .order_by(Gallery.id))
        rows = [model_to_dict(gallery, backrefs=True, manytomany=True)
                for gallery in query]
        self.assertEqual(rows, [
            {
                'id': 1,
                'name': 'family',
                'owner': {'id': 1, 'name': 'charlie'},
                'labels': [{'id': 1, 'label': 'nuggie'},
                           {'id': 2, 'label': 'bearbe'}],
            },
            {
                'id': 3,
                'name': 'misc',
                'owner': {'id': 2, 'name': 'peewee'},
                'labels': [{'id': 1, 'label': 'nuggie'},
                           {'id': 3, 'label': 'huey'}],
            }])

    @requires_models(Student, Course, StudentCourse)
    def test_manytomany_deferred(self):
        data = (
            ('s1', ('ca', 'cb', 'cc')),
            ('s2', ('cb', 'cd')),
            ('s3', ()))
        c = {}
        for student, courses in data:
            s = Student.create(name=student)
            for course in courses:
                if course not in c:
                    c[course] = Course.create(name=course)
                StudentCourse.create(student=s, course=c[course])

        query = Student.select().order_by(Student.name)
        data = []
        for user in query:
            user_dict = model_to_dict(user, manytomany=True)
            user_dict['courses'].sort(key=operator.itemgetter('id'))
            data.append(user_dict)

        self.assertEqual(data, [
            {'id': 1, 'name': 's1', 'courses': [
                {'id': 1, 'name': 'ca'},
                {'id': 2, 'name': 'cb'},
                {'id': 3, 'name': 'cc'}]},
            {'id': 2, 'name': 's2', 'courses': [
                {'id': 2, 'name': 'cb'},
                {'id': 4, 'name': 'cd'}]},
            {'id': 3, 'name': 's3', 'courses': []}])

        query = Course.select().order_by(Course.name)
        data = []
        for course in query:
            course_dict = model_to_dict(course, manytomany=True)
            course_dict['students'].sort(key=operator.itemgetter('id'))
            data.append(course_dict)

        self.assertEqual(data, [
            {'id': 1, 'name': 'ca', 'students': [
                {'id': 1, 'name': 's1'}]},
            {'id': 2, 'name': 'cb', 'students': [
                {'id': 1, 'name': 's1'},
                {'id': 2, 'name': 's2'}]},
            {'id': 3, 'name': 'cc', 'students': [
                {'id': 1, 'name': 's1'}]},
            {'id': 4, 'name': 'cd', 'students': [
                {'id': 2, 'name': 's2'}]}])

    def test_recurse_max_depth(self):
        t0, t1, t2 = [Tweet.create(user=self.user, content='t%s' % i)
                      for i in range(3)]
        tag0, tag1 = [Tag.create(tag=t) for t in ['tag0', 'tag1']]
        TweetTag.create(tweet=t0, tag=tag0)
        TweetTag.create(tweet=t0, tag=tag1)
        TweetTag.create(tweet=t1, tag=tag1)

        data = model_to_dict(self.user, recurse=True, backrefs=True)
        self.assertEqual(data, {
            'id': self.user.id,
            'username': 'peewee',
            'tweets': [
                {'id': t0.id, 'content': 't0', 'tweettag_set': [
                    {'tag': {'tag': 'tag0', 'id': tag0.id}},
                    {'tag': {'tag': 'tag1', 'id': tag1.id}},
                ]},
                {'id': t1.id, 'content': 't1', 'tweettag_set': [
                    {'tag': {'tag': 'tag1', 'id': tag1.id}},
                ]},
                {'id': t2.id, 'content': 't2', 'tweettag_set': []},
            ]})

        data = model_to_dict(self.user, recurse=True, backrefs=True,
                             max_depth=2)
        self.assertEqual(data, {
            'id': self.user.id,
            'username': 'peewee',
            'tweets': [
                {'id': t0.id, 'content': 't0', 'tweettag_set': [
                    {'tag': tag0.id}, {'tag': tag1.id},
                ]},
                {'id': t1.id, 'content': 't1', 'tweettag_set': [
                    {'tag': tag1.id},
                ]},
                {'id': t2.id, 'content': 't2', 'tweettag_set': []},
            ]})

        data = model_to_dict(self.user, recurse=True, backrefs=True,
                             max_depth=1)
        self.assertEqual(data, {
            'id': self.user.id,
            'username': 'peewee',
            'tweets': [
                {'id': t0.id, 'content': 't0'},
                {'id': t1.id, 'content': 't1'},
                {'id': t2.id, 'content': 't2'}]})

        self.assertEqual(model_to_dict(self.user, recurse=True, backrefs=True,
                                       max_depth=0),
                         {'id': self.user.id, 'username': 'peewee'})

    def test_only(self):
        username_dict = {'username': 'peewee'}
        self.assertEqual(model_to_dict(self.user, only=[User.username]),
                         username_dict)

        self.assertEqual(
            model_to_dict(self.user, backrefs=True, only=[User.username]),
            username_dict)

        tweet = Tweet.create(user=self.user, content='t0')
        tweet_dict = {'content': 't0', 'user': {'username': 'peewee'}}
        field_list = [Tweet.content, Tweet.user, User.username]
        self.assertEqual(model_to_dict(tweet, only=field_list),
                         tweet_dict)
        self.assertEqual(model_to_dict(tweet, backrefs=True, only=field_list),
                         tweet_dict)

        tweet_dict['user'] = self.user.id
        self.assertEqual(model_to_dict(tweet, backrefs=True, recurse=False,
                                       only=field_list),
                         tweet_dict)

    def test_exclude(self):
        self.assertEqual(model_to_dict(self.user, exclude=[User.id]),
                         {'username': 'peewee'})

        # Exclude the foreign key using FK field and backref.
        self.assertEqual(model_to_dict(self.user, backrefs=True,
                                       exclude=[User.id, Tweet.user]),
                         {'username': 'peewee'})
        self.assertEqual(model_to_dict(self.user, backrefs=True,
                                       exclude=[User.id, User.tweets]),
                         {'username': 'peewee'})

        tweet = Tweet.create(user=self.user, content='t0')
        fields = [Tweet.tweettag_set, Tweet.id, Tweet.user]
        self.assertEqual(model_to_dict(tweet, backrefs=True, exclude=fields),
                         {'content': 't0'})
        fields[-1] = User.id
        self.assertEqual(model_to_dict(tweet, backrefs=True, exclude=fields),
                         {'content': 't0', 'user': {'username': 'peewee'}})

    def test_extra_attrs(self):
        with self.assertQueryCount(0):
            extra = ['name_hash']
            self.assertEqual(model_to_dict(self.user, extra_attrs=extra), {
                'id': self.user.id,
                'username': 'peewee',
                'name_hash': 5})

        with self.assertQueryCount(0):
            self.assertRaises(AttributeError, model_to_dict, self.user,
                              extra_attrs=['xx'])

    def test_fields_from_query(self):
        User.delete().execute()
        for i in range(3):
            user = User.create(username='u%d' % i)
            for x in range(i + 1):
                Tweet.create(user=user, content='%s-%s' % (user.username, x))

        query = (User
                 .select(User.username, fn.COUNT(Tweet.id).alias('ct'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User.username)
                 .order_by(User.id))
        with self.assertQueryCount(1):
            u0, u1, u2 = list(query)
            self.assertEqual(model_to_dict(u0, fields_from_query=query), {
                'username': 'u0',
                'ct': 1})
            self.assertEqual(model_to_dict(u2, fields_from_query=query), {
                'username': 'u2',
                'ct': 3})

        query = (Tweet
                 .select(Tweet, User, SQL('1337').alias('magic'))
                 .join(User)
                 .order_by(Tweet.id)
                 .limit(1))
        with self.assertQueryCount(1):
            tweet, = query
            self.assertEqual(model_to_dict(tweet, fields_from_query=query), {
                'id': tweet.id,
                'content': 'u0-0',
                'magic': 1337,
                'user': {'id': tweet.user_id, 'username': 'u0'}})

            self.assertEqual(model_to_dict(tweet, fields_from_query=query,
                                           exclude=[User.id, Tweet.id]),
                             {'magic': 1337, 'content': 'u0-0',
                              'user': {'username': 'u0'}})

    def test_only_backref(self):
        for i in range(3):
            Tweet.create(user=self.user, content=str(i))

        data = model_to_dict(self.user, backrefs=True, only=[
            User.username,
            User.tweets,
            Tweet.content])
        if 'tweets' in data:
            data['tweets'].sort(key=lambda t: t['content'])
        self.assertEqual(data, {
            'username': 'peewee',
            'tweets': [
                {'content': '0'},
                {'content': '1'},
                {'content': '2'}]})

    @requires_models(Host, Service, Device)
    def test_model_to_dict_disabled_backref(self):
        host = Host.create(name='pi')
        Device.create(host=host, name='raspberry pi')
        Service.create(host=host, name='ssh')
        Service.create(host=host, name='vpn')

        data = model_to_dict(host, recurse=True, backrefs=True)
        services = sorted(data.pop('services'), key=operator.itemgetter('id'))
        self.assertEqual(data, {'id': 1, 'name': 'pi'})
        self.assertEqual(services, [
            {'id': 1, 'name': 'ssh'},
            {'id': 2, 'name': 'vpn'}])

    @requires_models(Basket, Item)
    def test_empty_vs_null_fk(self):
        b = Basket.create(id=0)
        i = Item.create(id=0, basket=b)

        data = model_to_dict(i)
        self.assertEqual(data, {'id': 0, 'basket': {'id': 0}})

        data = model_to_dict(i, recurse=False)
        self.assertEqual(data, {'id': 0, 'basket': 0})


class TestDictToModel(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Tweet, Tag, TweetTag]

    def setUp(self):
        super(TestDictToModel, self).setUp()
        self.user = User.create(username='peewee')

    def test_simple(self):
        data = {'username': 'peewee', 'id': self.user.id}
        inst = dict_to_model(User, data)
        self.assertTrue(isinstance(inst, User))
        self.assertEqual(inst.username, 'peewee')
        self.assertEqual(inst.id, self.user.id)

    def test_update_model_from_dict(self):
        data = {'content': 'tweet', 'user': {'username': 'zaizee'}}
        with self.assertQueryCount(0):
            user = User(id=3, username='orig')
            tweet = Tweet(id=4, content='orig', user=user)

            obj = update_model_from_dict(tweet, data)

        self.assertEqual(obj.id, 4)
        self.assertEqual(obj.content, 'tweet')
        self.assertEqual(obj.user.id, 3)
        self.assertEqual(obj.user.username, 'zaizee')

    def test_related(self):
        data = {
            'id': 2,
            'content': 'tweet-1',
            'user': {'id': self.user.id, 'username': 'peewee'}}

        with self.assertQueryCount(0):
            inst = dict_to_model(Tweet, data)
            self.assertTrue(isinstance(inst, Tweet))
            self.assertEqual(inst.id, 2)
            self.assertEqual(inst.content, 'tweet-1')
            self.assertTrue(isinstance(inst.user, User))
            self.assertEqual(inst.user.id, self.user.id)
            self.assertEqual(inst.user.username, 'peewee')

        data['user'] = self.user.id

        with self.assertQueryCount(0):
            inst = dict_to_model(Tweet, data)

        with self.assertQueryCount(1):
            self.assertEqual(inst.user, self.user)

    def test_backrefs(self):
        data = {
            'id': self.user.id,
            'username': 'peewee',
            'tweets': [
                {'id': 1, 'content': 't1'},
                {'id': 2, 'content': 't2'},
            ]}

        with self.assertQueryCount(0):
            inst = dict_to_model(User, data)
            self.assertEqual(inst.id, self.user.id)
            self.assertEqual(inst.username, 'peewee')
            self.assertTrue(isinstance(inst.tweets, list))

            t1, t2 = inst.tweets
            self.assertEqual(t1.id, 1)
            self.assertEqual(t1.content, 't1')
            self.assertEqual(t1.user, self.user)

            self.assertEqual(t2.id, 2)
            self.assertEqual(t2.content, 't2')
            self.assertEqual(t2.user, self.user)

    def test_unknown_attributes(self):
        data = {
            'id': self.user.id,
            'username': 'peewee',
            'xx': 'does not exist'}
        self.assertRaises(AttributeError, dict_to_model, User, data)

        inst = dict_to_model(User, data, ignore_unknown=True)
        self.assertEqual(inst.xx, 'does not exist')

    def test_ignore_id_attribute(self):
        class Register(Model):
            key = CharField(primary_key=True)

        data = {'id': 100, 'key': 'k1'}
        self.assertRaises(AttributeError, dict_to_model, Register, data)

        inst = dict_to_model(Register, data, ignore_unknown=True)
        self.assertEqual(inst.__data__, {'key': 'k1'})

        class Base(Model):
            class Meta:
                primary_key = False

        class Register2(Model):
            key = CharField(primary_key=True)

        self.assertRaises(AttributeError, dict_to_model, Register2, data)

        inst = dict_to_model(Register2, data, ignore_unknown=True)
        self.assertEqual(inst.__data__, {'key': 'k1'})


class ReconnectMySQLDatabase(ReconnectMixin, MySQLDatabase):
    def cursor(self, commit):
        cursor = super(ReconnectMySQLDatabase, self).cursor(commit)

        # The first (0th) query fails, as do all queries after the 2nd (1st).
        if self._query_counter != 1:
            def _fake_execute(self, _):
                raise OperationalError('2006')
            cursor.execute = _fake_execute
        self._query_counter += 1
        return cursor

    def close(self):
        self._close_counter += 1
        return super(ReconnectMySQLDatabase, self).close()

    def _reset_mock(self):
        self._close_counter = 0
        self._query_counter = 0


@requires_mysql
class TestReconnectMixin(DatabaseTestCase):
    database = db_loader('mysql', db_class=ReconnectMySQLDatabase)

    def test_reconnect_mixin(self):
        # Verify initial state.
        self.database._reset_mock()
        self.assertEqual(self.database._close_counter, 0)

        sql = 'select 1 + 1'
        curs = self.database.execute_sql(sql)
        self.assertEqual(curs.fetchone(), (2,))
        self.assertEqual(self.database._close_counter, 1)

        # Due to how we configured our mock, our queries are now failing and we
        # can verify a reconnect is occuring *AND* the exception is propagated.
        self.assertRaises(OperationalError, self.database.execute_sql, sql)
        self.assertEqual(self.database._close_counter, 2)

        # We reset the mock counters. The first query we execute will fail. The
        # second query will succeed (which happens automatically, thanks to the
        # retry logic).
        self.database._reset_mock()
        curs = self.database.execute_sql(sql)
        self.assertEqual(curs.fetchone(), (2,))
        self.assertEqual(self.database._close_counter, 1)
