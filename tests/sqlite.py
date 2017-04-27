import os

from peewee import *
from peewee import sqlite3
from playhouse.sqlite_ext import *

from .base import ModelTestCase
from .base import TestModel
from .base import skip_case_unless


database = SqliteExtDatabase(':memory:', timeout=0.1)


CLOSURE_EXTENSION = os.environ.get('PEEWEE_CLOSURE_EXTENSION')
if not CLOSURE_EXTENSION and os.path.exists('closure.so'):
    CLOSURE_EXTENSION = 'closure.so'


class WeightedAverage(object):
    def __init__(self):
        self.total = 0.
        self.count = 0.

    def step(self, value, weight=None):
        weight = weight or 1.
        self.total += weight
        self.count += (weight * value)

    def finalize(self):
        if self.total != 0.:
            return self.count / self.total
        return 0.

def _cmp(l, r):
    if l < r:
        return -1
    return 1 if r < l else 0

def collate_reverse(s1, s2):
    return -_cmp(s1, s2)

@database.collation()
def collate_case_insensitive(s1, s2):
    return _cmp(s1.lower(), s2.lower())

def title_case(s): return s.title()

@database.func()
def rstrip(s, n):
    return s.rstrip(n)

database.register_aggregate(WeightedAverage, 'weighted_avg', 1)
database.register_aggregate(WeightedAverage, 'weighted_avg', 2)
database.register_collation(collate_reverse)
database.register_function(title_case)


class Post(TestModel):
    message = TextField()


class ContentPost(Post, FTSModel):
    class Meta:
        options = {
            'content': Post,
            'tokenize': 'porter'}


class ContentPostMessage(TestModel, FTSModel):
    message = TextField()
    class Meta:
        options = {'tokenize': 'porter', 'content': Post.message}


class Document(TestModel, FTSModel):
    message = TextField()
    class Meta:
        options = {'tokenize': 'porter'}


class MultiColumn(TestModel, FTSModel):
    c1 = TextField()
    c2 = TextField()
    c3 = TextField()
    c4 = IntegerField()
    class Meta:
        options = {'tokenize': 'porter'}


class RowIDModel(TestModel):
    rowid = RowIDField()
    data = IntegerField()


class APIData(TestModel):
    data = JSONField()
    value = TextField()


def json_installed():
    if sqlite3.sqlite_version_info < (3, 9, 0):
        return False
    # Test in-memory DB to determine if the FTS5 extension is installed.
    tmp_db = sqlite3.connect(':memory:')
    try:
        tmp_db.execute('select json(?)', (1337,))
    except:
        return False
    finally:
        tmp_db.close()
    return True


@skip_case_unless(json_installed)
class TestJSONField(ModelTestCase):
    database = database
    requires = [APIData]
    test_data = [
        {'metadata': {'tags': ['python', 'sqlite']},
         'title': 'My List of Python and SQLite Resources',
         'url': 'http://charlesleifer.com/blog/my-list-of-python-and-sqlite-resources/'},
        {'metadata': {'tags': ['nosql', 'python', 'sqlite', 'cython']},
         'title': "Using SQLite4's LSM Storage Engine as a Stand-alone NoSQL Database with Python",
         'url': 'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/'},
        {'metadata': {'tags': ['sqlite', 'search', 'python', 'peewee']},
         'title': 'Building the SQLite FTS5 Search Extension',
         'url': 'http://charlesleifer.com/blog/building-the-sqlite-fts5-search-extension/'},
        {'metadata': {'tags': ['nosql', 'python', 'unqlite', 'cython']},
         'title': 'Introduction to the fast new UnQLite Python Bindings',
         'url': 'http://charlesleifer.com/blog/introduction-to-the-fast-new-unqlite-python-bindings/'},
        {'metadata': {'tags': ['python', 'walrus', 'redis', 'nosql']},
         'title': 'Alternative Redis-Like Databases with Python',
         'url': 'http://charlesleifer.com/blog/alternative-redis-like-databases-with-python/'},
    ]

    def setUp(self):
        super(TestJSONField, self).setUp()
        for entry in self.test_data:
            APIData.create(data=entry, value=entry['title'])
        self.Q = APIData.select().order_by(APIData.id)

    def test_extract(self):
        titles = self.Q.columns(APIData.data.extract('title')).tuples()
        self.assertEqual([row for row, in titles], [
            'My List of Python and SQLite Resources',
            'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'Building the SQLite FTS5 Search Extension',
            'Introduction to the fast new UnQLite Python Bindings',
            'Alternative Redis-Like Databases with Python',
        ])

        tags = (self.Q
                .columns(APIData.data.extract('metadata.tags').alias('tags'))
                .dicts())
        self.assertEqual(list(tags), [
            {'tags': ['python', 'sqlite']},
            {'tags': ['nosql', 'python', 'sqlite', 'cython']},
            {'tags': ['sqlite', 'search', 'python', 'peewee']},
            {'tags': ['nosql', 'python', 'unqlite', 'cython']},
            {'tags': ['python', 'walrus', 'redis', 'nosql']},
        ])

        missing = self.Q.columns(APIData.data.extract('foo.bar')).tuples()
        self.assertEqual([row for row, in missing], [None] * 5)

    def test_length(self):
        tag_len = (self.Q
                   .columns(APIData.data.length('metadata.tags').alias('len'))
                   .dicts())
        self.assertEqual(list(tag_len), [
            {'len': 2},
            {'len': 4},
            {'len': 4},
            {'len': 4},
            {'len': 4},
        ])

    def test_remove(self):
        query = (self.Q
                 .columns(
                     fn.json_extract(
                         APIData.data.remove('metadata.tags'),
                         '$.metadata'))
                 .tuples())
        self.assertEqual([row for row, in query], ['{}'] * 5)

        Clone = APIData.alias()
        query = (APIData
                 .update(
                     data=(Clone
                           .select(Clone.data.remove('metadata.tags[2]'))
                           .where(Clone.id == APIData.id)))
                 .where(
                     APIData.value.contains('LSM Storage') |
                     APIData.value.contains('UnQLite Python')))
        result = query.execute()
        self.assertEqual(result, 2)

        tag_len = (self.Q
                   .columns(APIData.data.length('metadata.tags').alias('len'))
                   .dicts())
        self.assertEqual(list(tag_len), [
            {'len': 2},
            {'len': 3},
            {'len': 4},
            {'len': 3},
            {'len': 4},
        ])

    def test_set(self):
        query = (self.Q
                 .columns(
                     fn.json_extract(
                         APIData.data.set(
                             'metadata',
                             {'k1': {'k2': 'bar'}}),
                         '$.metadata.k1'))
                 .tuples())
        self.assertEqual(
            [json.loads(row) for row, in query],
            [{'k2': 'bar'}] * 5)

        Clone = APIData.alias()
        query = (APIData
                 .update(
                     data=(Clone
                           .select(Clone.data.set('title', 'hello'))
                           .where(Clone.id == APIData.id)))
                 .where(APIData.value.contains('LSM Storage'))
                 .execute())
        self.assertEqual(query, 1)

        titles = self.Q.columns(APIData.data.extract('title')).tuples()
        for idx, (row,) in enumerate(titles):
            if idx == 1:
                self.assertEqual(row, 'hello')
            else:
                self.assertNotEqual(row, 'hello')

    def test_multi_set(self):
        Clone = APIData.alias()
        set_query = (Clone
                     .select(Clone.data.set(
                         'foo', 'foo value',
                         'tagz', ['list', 'of', 'tags'],
                         'x.y.z', 3,
                         'metadata.foo', None,
                         'bar.baze', True))
                     .where(Clone.id == APIData.id))
        query = (APIData
                 .update(data=set_query)
                 .where(APIData.value.contains('LSM Storage'))
                 .execute())
        self.assertEqual(query, 1)

        result = APIData.select().where(APIData.value.contains('LSM storage')).get()
        self.assertEqual(result.data, {
            'bar': {'baze': 1},
            'foo': 'foo value',
            'metadata': {'tags': ['nosql', 'python', 'sqlite', 'cython'], 'foo': None},
            'tagz': ['list', 'of', 'tags'],
            'title': 'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'url': 'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/',
            'x': {'y': {'z': 3}},
        })

    """
    def test_children(self):
        children = APIData.data.children().alias('children')
        query = (APIData
                 .select(children.c.value.alias('value'))
                 .from_(APIData, children)
                 .where(children.c.key.in_(['title', 'url']))
                 .order_by(SQL('1'))
                 .tuples())
        self.assertEqual([row for row, in query], [
            'Alternative Redis-Like Databases with Python',
            'Building the SQLite FTS5 Search Extension',
            'Introduction to the fast new UnQLite Python Bindings',
            'My List of Python and SQLite Resources',
            'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'http://charlesleifer.com/blog/alternative-redis-like-databases-with-python/',
            'http://charlesleifer.com/blog/building-the-sqlite-fts5-search-extension/',
            'http://charlesleifer.com/blog/introduction-to-the-fast-new-unqlite-python-bindings/',
            'http://charlesleifer.com/blog/my-list-of-python-and-sqlite-resources/',
            'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/',
        ])
    """
