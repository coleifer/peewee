import datetime
import unittest

from peewee import *
from playhouse.sqlite_ext import *
from playhouse.sqlite_ext import _VirtualFieldMixin
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.libs import mock

try:
    from playhouse import _sqlite_ext
except ImportError:
    raise ImportError('Unable to load `_sqlite_ext` C extension.')

db = SqliteExtDatabase(':memory:')

class BaseModel(Model):
    class Meta:
        database = db

class Note(BaseModel):
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class NoteIndex(FTSModel):
    docid = DocIDField()
    content = SearchField()

    class Meta:
        database = db
        extension_options = {'tokenize': 'porter'}

    @classmethod
    def index_note(cls, note):
        return NoteIndex.insert({
            NoteIndex.docid: note.id,
            NoteIndex.content: note.content}).execute()


class BaseTestCase(ModelTestCase):
    requires = [Note, NoteIndex]

    def setUp(self):
        super(BaseTestCase, self).setUp()
        functions_to_patch = [
            'peewee._sqlite_date_part',
            'peewee._sqlite_date_trunc',
            'peewee._sqlite_regexp',
            'playhouse.sqlite_ext.bm25',
            'playhouse.sqlite_ext.rank',
        ]
        def uncallable(fn):
            def side_effect():
                raise AssertionError(fn.__name__)
            return side_effect
        self._patches = [
            mock.patch(fn, side_effect=uncallable(fn))
            for fn in functions_to_patch]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        super(BaseTestCase, self).tearDown()
        if not db.is_closed():
            db.close()
        for patch in self._patches:
            patch.stop()


class TestRank(BaseTestCase):
    test_content = (
        ('A faith is a necessity to a man. Woe to him who believes in '
         'nothing.'),
        ('All who call on God in true faith, earnestly from the heart, will '
         'certainly be heard, and will receive what they have asked and '
         'desired.'),
        ('Be faithful in small things because it is in them that your '
         'strength lies.'),
        ('Faith consists in believing when it is beyond the power of reason '
         'to believe.'),
        ('Faith has to do with things that are not seen and hope with things '
         'that are not at hand.'))

    def setUp(self):
        super(TestRank, self).setUp()
        with db.atomic():
            for content in self.test_content:
                note = Note.create(content=content)
                NoteIndex.index_note(note)

    def test_scoring_lucene(self):
        query = NoteIndex.search_lucene('things', [1.0], with_score=True)
        results = [(item[0], round(item[1], 2)) for item in query.tuples()]
        self.assertEqual(results, [
            (self.test_content[4], -0.17),
            (self.test_content[2], -0.14)])

        query = NoteIndex.search_lucene('faithful thing', [1.0], with_score=True)
        results = [(item[0], round(item[1], 2)) for item in query.tuples()]
        self.assertEqual(results, [
            (self.test_content[4], 0.08),
            (self.test_content[2], 0.1)])

    def test_scoring(self):
        query = NoteIndex.search('things', with_score=True).tuples()
        self.assertEqual(query[:], [
            (self.test_content[4], -2.0 / 3),
            (self.test_content[2], -1.0 / 3),
        ])

        query = NoteIndex.search('faithful', with_score=True).tuples()
        self.assertEqual([row[1] for row in query[:]], [
            -.2, -.2, -.2, -.2, -.2
        ])

    def test_scoring_bm25(self):
        query = NoteIndex.search_bm25('things', [1.0], with_score=True)
        results = [(item[0], round(item[1], 2)) for item in query.tuples()]
        self.assertEqual(results, [
            (self.test_content[4], -.45),
            (self.test_content[2], -.36),
        ])

        query = (NoteIndex
                 .select(NoteIndex.content,
                         fn.fts_bm25(
                             fn.matchinfo(NoteIndex.as_entity(), 'pcnalx'),
                             1.0).alias('score'))
                 .where(NoteIndex.match('things'))
                 .order_by(SQL('score'))
                 .tuples())

        results = [(item[0], round(item[1], 2)) for item in query]
        self.assertEqual(results, [
            (self.test_content[4], -.45),
            (self.test_content[2], -.36),
        ])


class TestRegexp(BaseTestCase):
    def setUp(self):
        super(TestRegexp, self).setUp()

        self.test_content = (
            'foo bar baz',
            'FOO nugBaRz',
            '01234 56789')
        for content in self.test_content:
            Note.create(content=content)

    def test_regexp(self):
        def assertMatches(regex, expected):
            query = (Note
                     .select(Note.content.regexp(regex))
                     .order_by(Note.id)
                     .tuples())
            self.assertEqual([row[0] for row in query], expected)

        assertMatches('foo', [1, 1, 0])
        assertMatches('BAR', [1, 1, 0])
        assertMatches('\\bBAR\\b', [1, 0, 0])
        assertMatches('[0-4]+', [0, 0, 1])
        assertMatches('[0-4]{5}', [0, 0, 1])
        assertMatches('[0-4]{6}', [0, 0, 0])

        assertMatches('', [1, 1, 1])
        assertMatches(None, [None, None, None])


class TestDateFunctions(BaseTestCase):
    def setUp(self):
        super(TestDateFunctions, self).setUp()

        dt = datetime.datetime
        self.test_datetimes = (
            dt(2000,  1,  2,  3,  4,  5, 6),
            dt(2001,  2,  3,  4,  5,  6),
            dt(1999, 12, 31, 23, 59, 59),
            dt(2010,  3,  1),
        )
        for i, value in enumerate(self.test_datetimes):
            Note.create(content=str(i), timestamp=value)

    def test_date_part(self):
        def Q(part):
            query = (Note
                     .select(fn.date_part(part, Note.timestamp))
                     .order_by(Note.id)
                     .tuples())
            return [row[0] for row in query]

        self.assertEqual(Q('year'), [2000, 2001, 1999, 2010])
        self.assertEqual(Q('month'), [1, 2, 12, 3])
        self.assertEqual(Q('day'), [2, 3, 31, 1])
        self.assertEqual(Q('hour'), [3, 4, 23, 0])
        self.assertEqual(Q('minute'), [4, 5, 59, 0])
        self.assertEqual(Q('second'), [5, 6, 59, 0])

        self.assertEqual(Q(None), [None, None, None, None])
        self.assertEqual(Q('foo'), [None, None, None, None])
        self.assertEqual(Q(''), [None, None, None, None])

        sql = 'SELECT date_part(?, ?)'

        result, = db.execute_sql(sql, ('year', None)).fetchone()
        self.assertIsNone(result)
        result, = db.execute_sql(sql, ('foo', None)).fetchone()
        self.assertIsNone(result)
        result, = db.execute_sql(sql, (None, None)).fetchone()
        self.assertIsNone(result)

    def test_date_trunc(self):
        def Q(part):
            query = (Note
                     .select(fn.date_trunc(part, Note.timestamp))
                     .order_by(Note.id)
                     .tuples())
            return [row[0] for row in query]

        self.assertEqual(Q('year'), ['2000', '2001', '1999', '2010'])
        self.assertEqual(Q('month'), [
            '2000-01',
            '2001-02',
            '1999-12',
            '2010-03'])
        self.assertEqual(Q('day'), [
            '2000-01-02',
            '2001-02-03',
            '1999-12-31',
            '2010-03-01'])
        self.assertEqual(Q('hour'), [
            '2000-01-02 03',
            '2001-02-03 04',
            '1999-12-31 23',
            '2010-03-01 00'])
        self.assertEqual(Q('minute'), [
            '2000-01-02 03:04',
            '2001-02-03 04:05',
            '1999-12-31 23:59',
            '2010-03-01 00:00'])
        self.assertEqual(Q('second'), [
            '2000-01-02 03:04:05',
            '2001-02-03 04:05:06',
            '1999-12-31 23:59:59',
            '2010-03-01 00:00:00'])

        self.assertEqual(Q(None), [None, None, None, None])
        self.assertEqual(Q('foo'), [None, None, None, None])
        self.assertEqual(Q(''), [None, None, None, None])


class TestMurmurHash(BaseTestCase):
    def assertHash(self, s, e):
        curs = db.execute_sql('select murmurhash(?)', (s,))
        result = curs.fetchone()[0]
        self.assertEqual(result, e)

    def test_murmur_hash(self):
        self.assertHash('testkey', 3599487917)
        self.assertHash('murmur', 4160318927)
        self.assertHash('', 0)
        self.assertHash('this is a test of a longer string', 3556042345)
        self.assertHash(None, None)
