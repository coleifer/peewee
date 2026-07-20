from peewee import *
from playhouse.sqlite_ext import FTS5Model
from playhouse.sqlite_ext import SearchField

from .base import ModelTestCase
from .base import requires_models
from .base import skip_unless


database = SqliteDatabase(':memory:')


class Doc(FTS5Model):
    title = SearchField()
    data = SearchField()
    misc = SearchField(unindexed=True)

    class Meta:
        database = database
        legacy_table_names = False


class OddColumns(FTS5Model):
    # Column names that are not valid fts5 barewords.
    name = SearchField(column_name='a-b')
    kw = SearchField(column_name='AND')

    class Meta:
        database = database
        legacy_table_names = False


@skip_unless(FTS5Model.fts5_installed(), 'requires fts5')
class TestWebQuery(ModelTestCase):
    database = database
    requires = [Doc]
    documents = (
        ('foo aa bb', 'aa bb cc ' * 10, 1),
        ('bar bb cc', 'bb cc dd ' * 9, 2),
        ('baze cc dd', 'cc dd ee ' * 8, 3),
        ('nug aa dd', 'bb cc ' * 7, 4))

    # Search-box input, and the fts5 query it must translate to. Every
    # translation is also executed, so the corpus doubles as a check that
    # anything the parser emits is a query fts5 accepts.
    corpus = (
        # Terms, phrases and prefixes.
        ('aa', '"aa"'),
        ('aa bb', '"aa" AND "bb"'),
        ('"cc dd"', '"cc dd"'),
        ('ba*', '"ba"*'),
        ('"cc dd"*', '"cc dd"*'),
        ('aa "cc dd" ba*', '"aa" AND "cc dd" AND "ba"*'),

        # Operators. Juxtaposition and AND are the same thing, and "-" is
        # an exclusion applying to the terms it is AND-ed with.
        ('aa AND bb', '"aa" AND "bb"'),
        ('aa OR bb', '"aa" OR "bb"'),
        ('aa NOT bb', '"aa" NOT "bb"'),
        ('aa -bb', '"aa" NOT "bb"'),
        ('aa bb -cc -dd', '("aa" AND "bb") NOT "cc" NOT "dd"'),
        ('aa OR -bb', '"aa"'),

        # Grouping. fts5 only allows implicit AND between phrases, so an
        # AND involving a group is always written out.
        ('(aa OR bb) cc', '("aa" OR "bb") AND "cc"'),
        ('(aa OR bb) NOT cc', '("aa" OR "bb") NOT "cc"'),
        ('aa OR (bb NOT cc)', '"aa" OR ("bb" NOT "cc")'),
        ('aa bb OR cc dd', '("aa" AND "bb") OR ("cc" AND "dd")'),
        ('((aa))', '"aa"'),

        # Column filters. Column names are quoted, as they need not be
        # valid fts5 barewords.
        ('title: aa', '"title": "aa"'),
        ('title:aa', '"title": "aa"'),
        ('title:"cc dd"', '"title": "cc dd"'),
        ('title:ba*', '"title": "ba"*'),
        ('title:(aa OR bb)', '"title": ("aa" OR "bb")'),
        ('title:(data:aa)', '"title": ("data": "aa")'),
        ('title:aa bb', '("title": "aa") AND "bb"'),
        ('aa -title:bb', '"aa" NOT ("title": "bb")'),
        ('{title data}: aa', '{"title" "data"}: "aa"'),
        ('{title data}:(aa OR bb)', '{"title" "data"}: ("aa" OR "bb")'),

        # Not column filters: unknown, and unindexed (can never match).
        ('nope: aa', '"nope:" AND "aa"'),
        ('misc: aa', '"misc:" AND "aa"'),
        ('re: hello', '"re:" AND "hello"'),

        # fts5 syntax with no search-box meaning is carried as text.
        ('covid-19', '"covid-19"'),
        ("o'brien", '"o\'brien"'),
        ('c++', '"c++"'),
        ('^aa', '"^aa"'),
        ('aa + bb', '"aa" AND "bb"'),
        ('NEAR(aa bb)', '"NEAR" AND ("aa" AND "bb")'),
    )

    def setUp(self):
        super(TestWebQuery, self).setUp()
        for title, data, misc in self.documents:
            Doc.create(title=title, data=data, misc=misc)

    def assertQuery(self, query, expected):
        self.assertEqual(Doc.web_query(query), expected, query)
        # Must be a query fts5 accepts.
        list(Doc.select().where(Doc.match(expected)))

    def test_translations(self):
        for query, expected in self.corpus:
            self.assertQuery(query, expected)

    def test_unbalanced(self):
        self.assertQuery('(aa OR bb', '"aa" OR "bb"')
        self.assertQuery('aa) OR bb', '"aa" OR "bb"')
        self.assertQuery('he said "foo', '"he" AND "said" AND "foo"')

        # A group is not absorbed into the enclosing scope by a stray
        # negation or column marker.
        self.assertQuery('aa (bb) OR cc', '("aa" AND "bb") OR "cc"')
        self.assertQuery('aa (bb -) OR cc', '("aa" AND "bb") OR "cc"')
        self.assertQuery('aa (title:) OR cc', '"aa" OR "cc"')

    def test_dangling_operators(self):
        self.assertQuery('NOT aa', '"aa"')
        self.assertQuery('aa AND', '"aa"')
        self.assertQuery('aa NOT', '"aa"')
        self.assertQuery('aa OR OR bb', '"aa" OR "bb"')

    def test_nesting_is_capped(self):
        # Nesting is flattened rather than exhausting the stack.
        self.assertQuery('(' * 500 + 'aa', '"aa"')
        self.assertQuery('(' * 500 + 'aa' + ')' * 500, '"aa"')

    def test_nothing_to_search_for(self):
        for query in ('', '   ', '""', '-', '--aa', 'title:-aa', '()', '+',
                      ',', '*'):
            self.assertQuery(query, '""')

    @requires_models(OddColumns)
    def test_column_names(self):
        # Column names are quoted, so names that are not valid barewords (or
        # are fts5 keywords) still produce a usable filter.
        OddColumns.insert({'rowid': 1, 'name': 'hello',
                           'kw': 'world'}).execute()

        def assertRows(query, expected):
            translated = OddColumns.web_query(query)
            rows = [r.rowid for r in
                    OddColumns.select().where(OddColumns.match(translated))]
            self.assertEqual(rows, expected, translated)

        self.assertEqual(OddColumns.web_query('{a-b}: hello'),
                         '{"a-b"}: "hello"')
        self.assertEqual(OddColumns.web_query('AND: world'), '"AND": "world"')
        assertRows('{a-b}: hello', [1])
        assertRows('AND: world', [1])
        assertRows('{a-b AND}: hello', [1])
        assertRows('{a-b}: world', [])

        # The bare form only matches word-character names, so "a-b:" is text.
        # The braced form is how such a column is filtered.
        self.assertEqual(OddColumns.web_query('a-b: hello'),
                         '"a-b:" AND "hello"')

    def test_search(self):
        # search() applies clean_query, which must leave a translation as-is.
        for query, _ in self.corpus:
            translated = Doc.web_query(query)
            self.assertEqual(Doc.clean_query(translated), translated)

        def search(term):
            return sorted(row.rowid for row in Doc.search(Doc.web_query(term)))

        self.assertEqual(search('aa'), [1, 4])
        self.assertEqual(search('aa bb'), [1, 4])
        self.assertEqual(search('aa OR ee'), [1, 3, 4])
        self.assertEqual(search('aa -dd'), [1])
        self.assertEqual(search('"cc dd"'), [2, 3])
        self.assertEqual(search('ba*'), [2, 3])
        self.assertEqual(search('title: aa'), [1, 4])
        self.assertEqual(search('title: (aa OR baze)'), [1, 3, 4])
        self.assertEqual(search('{title data}: ee'), [3])
        self.assertEqual(search('dd -title:nug'), [2, 3])
        self.assertEqual(search('(aa OR baze) dd'), [3, 4])
        self.assertEqual(search('covid-19 aa'), [])
        self.assertEqual(search(''), [])
