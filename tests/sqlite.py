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
