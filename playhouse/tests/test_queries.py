from peewee import DeleteQuery
from peewee import InsertQuery
from peewee import prefetch_add_subquery
from peewee import RawQuery
from peewee import strip_parens
from peewee import SelectQuery
from peewee import UpdateQuery
from playhouse.tests.base import compiler
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import normal_compiler
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if
from playhouse.tests.base import test_db
from playhouse.tests.base import TestDatabase
from playhouse.tests.base import TestModel
from playhouse.tests.models import *


class TestSelectQuery(PeeweeTestCase):
    def test_selection(self):
        sq = SelectQuery(User)
        self.assertSelect(sq, '"users"."id", "users"."username"', [])

        sq = SelectQuery(Blog, Blog.pk, Blog.title, Blog.user, User.username).join(User)
        self.assertSelect(sq, '"blog"."pk", "blog"."title", "blog"."user_id", "users"."username"', [])

        sq = SelectQuery(User, fn.Lower(fn.Substr(User.username, 0, 1)).alias('lu'), fn.Count(Blog.pk)).join(Blog)
        self.assertSelect(sq, 'Lower(Substr("users"."username", ?, ?)) AS lu, Count("blog"."pk")', [0, 1])

        sq = SelectQuery(User, User.username, fn.Count(Blog.select().where(Blog.user == User.id)))
        self.assertSelect(sq, '"users"."username", Count(SELECT "blog"."pk" FROM "blog" AS blog WHERE ("blog"."user_id" = "users"."id"))', [])

        sq = SelectQuery(Package, Package, fn.Count(PackageItem.id)).join(PackageItem)
        self.assertSelect(sq, '"package"."id", "package"."barcode", Count("packageitem"."id")', [])

    def test_select_distinct(self):
        sq = SelectQuery(User).distinct()
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT "users"."id", "users"."username" '
             'FROM "users" AS users', []))

        sq = sq.distinct(False)
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT "users"."id", "users"."username" FROM "users" AS users', []))

        sq = SelectQuery(User).distinct([User.username])
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT ON ("users"."username") "users"."id", '
             '"users"."username" '
             'FROM "users" AS users', []))

        sq = SelectQuery(Blog).distinct([Blog.user, Blog.title])
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT ON ("blog"."user_id", "blog"."title") '
             '"blog"."pk", "blog"."user_id", "blog"."title", "blog"."content",'
             ' "blog"."pub_date" '
             'FROM "blog" AS blog', []))

        sq = SelectQuery(Blog, Blog.user, Blog.title).distinct(
            [Blog.user, Blog.title])
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT ON ("blog"."user_id", "blog"."title") '
             '"blog"."user_id", "blog"."title" '
             'FROM "blog" AS blog', []))

    def test_reselect(self):
        sq = SelectQuery(User, User.username)
        self.assertSelect(sq, '"users"."username"', [])

        sq2 = sq.select()
        self.assertSelect(sq2, '"users"."id", "users"."username"', [])
        self.assertTrue(id(sq) != id(sq2))

        sq3 = sq2.select(User.id)
        self.assertSelect(sq3, '"users"."id"', [])
        self.assertTrue(id(sq2) != id(sq3))

    def test_select_subquery(self):
        subquery = SelectQuery(Child, fn.Count(Child.id)).where(Child.parent == Parent.id).group_by(Child.parent)
        sq = SelectQuery(Parent, Parent, subquery.alias('count'))

        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT "parent"."id", "parent"."data", ' + \
            '(SELECT Count("child"."id") FROM "child" AS child ' + \
            'WHERE ("child"."parent_id" = "parent"."id") GROUP BY "child"."parent_id") ' + \
            'AS count FROM "parent" AS parent', []
        ))

    def test_select_subquery_ordering(self):
        sq = Comment.select().join(Blog).where(Blog.pk == 1)
        sq1 = Comment.select().where(
            (Comment.id << sq) |
            (Comment.comment == '*')
        )
        sq2 = Comment.select().where(
            (Comment.comment == '*') |
            (Comment.id << sq)
        )

        sql1, params1 = normal_compiler.generate_select(sq1)
        self.assertEqual(sql1, (
            'SELECT "t1"."id", "t1"."blog_id", "t1"."comment" FROM "comment" AS t1 '
            'WHERE (("t1"."id" IN ('
            'SELECT "t2"."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON ("t2"."blog_id" = "t3"."pk") '
            'WHERE ("t3"."pk" = ?))) OR ("t1"."comment" = ?))'))
        self.assertEqual(params1, [1, '*'])

        sql2, params2 = normal_compiler.generate_select(sq2)
        self.assertEqual(sql2, (
            'SELECT "t1"."id", "t1"."blog_id", "t1"."comment" FROM "comment" AS t1 '
            'WHERE (("t1"."comment" = ?) OR ("t1"."id" IN ('
            'SELECT "t2"."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON ("t2"."blog_id" = "t3"."pk") '
            'WHERE ("t3"."pk" = ?))))'))
        self.assertEqual(params2, ['*', 1])

    def test_multiple_subquery(self):
        sq2 = Comment.select().where(Comment.comment == '2').join(Blog)
        sq1 = Comment.select().where(
            (Comment.comment == '1') &
            (Comment.id << sq2)
        ).join(Blog)
        sq = Comment.select().where(
            Comment.id << sq1
        )
        sql, params = normal_compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."blog_id", "t1"."comment" '
            'FROM "comment" AS t1 '
            'WHERE ("t1"."id" IN ('
            'SELECT "t2"."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON ("t2"."blog_id" = "t3"."pk") '
            'WHERE (("t2"."comment" = ?) AND ("t2"."id" IN ('
            'SELECT "t4"."id" FROM "comment" AS t4 '
            'INNER JOIN "blog" AS t5 ON ("t4"."blog_id" = "t5"."pk") '
            'WHERE ("t4"."comment" = ?)'
            ')))))'))
        self.assertEqual(params, ['1', '2'])

    def test_select_cloning(self):
        ct = fn.Count(Blog.pk)
        sq = SelectQuery(User, User, User.id.alias('extra_id'), ct.alias('blog_ct')).join(
            Blog, JOIN.LEFT_OUTER).group_by(User).order_by(ct.desc())
        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username", "users"."id" AS extra_id, Count("blog"."pk") AS blog_ct ' + \
            'FROM "users" AS users LEFT OUTER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id") ' + \
            'GROUP BY "users"."id", "users"."username" ' + \
            'ORDER BY Count("blog"."pk") DESC', []
        ))
        self.assertEqual(User.id._alias, None)

    def test_joins(self):
        sq = SelectQuery(User).join(Blog)
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])

        sq = SelectQuery(Blog).join(User, JOIN.LEFT_OUTER)
        self.assertJoins(sq, ['LEFT OUTER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")'])

        sq = SelectQuery(User).join(Relationship)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON ("users"."id" = "relationship"."from_user_id")'])

        sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON ("users"."id" = "relationship"."to_user_id")'])

        sq = SelectQuery(User).join(Relationship, JOIN.LEFT_OUTER, Relationship.to_user)
        self.assertJoins(sq, ['LEFT OUTER JOIN "relationship" AS relationship ON ("users"."id" = "relationship"."to_user_id")'])

        sq = SelectQuery(Package).join(PackageItem)
        self.assertJoins(sq, ['INNER JOIN "packageitem" AS packageitem ON ("package"."barcode" = "packageitem"."package_id")'])

        sq = SelectQuery(PackageItem).join(Package)
        self.assertJoins(sq, ['INNER JOIN "package" AS package ON ("packageitem"."package_id" = "package"."barcode")'])

        sq = (SelectQuery(TestModelA)
              .join(TestModelB, on=(TestModelA.data == TestModelB.data))
              .join(TestModelC, on=(TestModelC.field == TestModelB.field)))
        self.assertJoins(sq, [
            'INNER JOIN "testmodelb" AS testmodelb ON ("testmodela"."data" = "testmodelb"."data")',
            'INNER JOIN "testmodelc" AS testmodelc ON ("testmodelc"."field" = "testmodelb"."field")',
        ])

        inner = SelectQuery(User).alias('j1')
        sq = SelectQuery(Blog).join(inner, on=(Blog.user == inner.c.id))
        join = ('INNER JOIN ('
                'SELECT "users"."id" FROM "users" AS users) AS j1 '
                'ON ("blog"."user_id" = "j1"."id")')
        self.assertJoins(sq, [join])

        inner_2 = SelectQuery(Comment).alias('j2')
        sq = sq.join(inner_2, on=(Blog.pk == inner_2.c.blog_id))
        join_2 = ('INNER JOIN ('
                  'SELECT "comment"."id" FROM "comment" AS comment) AS j2 '
                  'ON ("blog"."pk" = "j2"."blog_id")')
        self.assertJoins(sq, [join, join_2])

        sq = sq.join(Comment)
        self.assertJoins(sq, [
            join,
            join_2,
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")'])

    def test_join_self_referential(self):
        sq = SelectQuery(Category).join(Category)
        self.assertJoins(sq, ['INNER JOIN "category" AS category ON ("category"."parent_id" = "category"."id")'])

    def test_join_self_referential_alias(self):
        Parent = Category.alias()
        sq = SelectQuery(Category, Category, Parent).join(Parent, on=(Category.parent == Parent.id)).where(
            Parent.name == 'parent name'
        ).order_by(Parent.name)
        self.assertSelect(sq, '"t1"."id", "t1"."parent_id", "t1"."name", "t2"."id", "t2"."parent_id", "t2"."name"', [], normal_compiler)
        self.assertJoins(sq, [
            'INNER JOIN "category" AS t2 ON ("t1"."parent_id" = "t2"."id")',
        ], normal_compiler)
        self.assertWhere(sq, '("t2"."name" = ?)', ['parent name'], normal_compiler)
        self.assertOrderBy(sq, '"t2"."name"', [], normal_compiler)

        Grandparent = Category.alias()
        sq = SelectQuery(Category, Category, Parent, Grandparent).join(
            Parent, on=(Category.parent == Parent.id)
        ).join(
            Grandparent, on=(Parent.parent == Grandparent.id)
        ).where(Grandparent.name == 'g1')
        self.assertSelect(sq, '"t1"."id", "t1"."parent_id", "t1"."name", "t2"."id", "t2"."parent_id", "t2"."name", "t3"."id", "t3"."parent_id", "t3"."name"', [], normal_compiler)
        self.assertJoins(sq, [
            'INNER JOIN "category" AS t2 ON ("t1"."parent_id" = "t2"."id")',
            'INNER JOIN "category" AS t3 ON ("t2"."parent_id" = "t3"."id")',
        ], normal_compiler)
        self.assertWhere(sq, '("t3"."name" = ?)', ['g1'], normal_compiler)

    def test_join_both_sides(self):
        sq = SelectQuery(Blog).join(Comment).switch(Blog).join(User)
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")',
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])

        sq = SelectQuery(Blog).join(User).switch(Blog).join(Comment)
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")',
        ])

    def test_join_switching(self):
        class Artist(TestModel):
            pass

        class Track(TestModel):
            artist = ForeignKeyField(Artist)

        class Release(TestModel):
            artist = ForeignKeyField(Artist)

        class ReleaseTrack(TestModel):
            track = ForeignKeyField(Track)
            release = ForeignKeyField(Release)

        class Genre(TestModel):
            pass

        class TrackGenre(TestModel):
            genre = ForeignKeyField(Genre)
            track = ForeignKeyField(Track)

        multiple_first = Track.select().join(ReleaseTrack).join(Release).switch(Track).join(Artist).switch(Track).join(TrackGenre).join(Genre)
        self.assertSelect(multiple_first, '"track"."id", "track"."artist_id"', [])
        self.assertJoins(multiple_first, [
            'INNER JOIN "artist" AS artist ON ("track"."artist_id" = "artist"."id")',
            'INNER JOIN "genre" AS genre ON ("trackgenre"."genre_id" = "genre"."id")',
            'INNER JOIN "release" AS release ON ("releasetrack"."release_id" = "release"."id")',
            'INNER JOIN "releasetrack" AS releasetrack ON ("track"."id" = "releasetrack"."track_id")',
            'INNER JOIN "trackgenre" AS trackgenre ON ("track"."id" = "trackgenre"."track_id")',
        ])

        single_first = Track.select().join(Artist).switch(Track).join(ReleaseTrack).join(Release).switch(Track).join(TrackGenre).join(Genre)
        self.assertSelect(single_first, '"track"."id", "track"."artist_id"', [])
        self.assertJoins(single_first, [
            'INNER JOIN "artist" AS artist ON ("track"."artist_id" = "artist"."id")',
            'INNER JOIN "genre" AS genre ON ("trackgenre"."genre_id" = "genre"."id")',
            'INNER JOIN "release" AS release ON ("releasetrack"."release_id" = "release"."id")',
            'INNER JOIN "releasetrack" AS releasetrack ON ("track"."id" = "releasetrack"."track_id")',
            'INNER JOIN "trackgenre" AS trackgenre ON ("track"."id" = "trackgenre"."track_id")',
        ])

    def test_joining_expr(self):
        class A(TestModel):
            uniq_a = CharField(primary_key=True)
        class B(TestModel):
            uniq_ab = CharField(primary_key=True)
            uniq_b = CharField()
        class C(TestModel):
            uniq_bc = CharField(primary_key=True)
        sq = A.select(A, B, C).join(
            B, on=(A.uniq_a == B.uniq_ab)
        ).join(
            C, on=(B.uniq_b == C.uniq_bc)
        )
        self.assertSelect(sq, '"a"."uniq_a", "b"."uniq_ab", "b"."uniq_b", "c"."uniq_bc"', [])
        self.assertJoins(sq, [
            'INNER JOIN "b" AS b ON ("a"."uniq_a" = "b"."uniq_ab")',
            'INNER JOIN "c" AS c ON ("b"."uniq_b" = "c"."uniq_bc")',
        ])

    def test_join_other_node_types(self):
        cond = fn.Magic(User.id, Blog.user).alias('magic')
        sq = User.select().join(Blog, on=cond)
        self.assertJoins(sq, [
            'INNER JOIN "blog" AS blog ON '
            'Magic("users"."id", "blog"."user_id")'])

        sq = User.select().join(Blog, on=Blog.user.as_entity(True))
        self.assertJoins(sq, [
            'INNER JOIN "blog" AS blog ON '
            '"blog"."user_id"'])

    def test_where(self):
        sq = SelectQuery(User).where(User.id < 5)
        self.assertWhere(sq, '("users"."id" < ?)', [5])

        sq = SelectQuery(Blog).where(Blog.user << sq)
        self.assertWhere(sq, '("blog"."user_id" IN (SELECT "users"."id" FROM "users" AS users WHERE ("users"."id" < ?)))', [5])

        p = SelectQuery(Package).where(Package.id == 2)
        sq = SelectQuery(PackageItem).where(PackageItem.package << p)
        self.assertWhere(sq, '("packageitem"."package_id" IN (SELECT "package"."barcode" FROM "package" AS package WHERE ("package"."id" = ?)))', [2])

    def test_orwhere(self):
        sq = SelectQuery(User).orwhere(User.id < 5)
        self.assertWhere(sq, '("users"."id" < ?)', [5])

        sq = sq.orwhere(User.id > 10)
        self.assertWhere(sq, '(("users"."id" < ?) OR ("users"."id" > ?))', [5, 10])

    def test_fix_null(self):
        sq = SelectQuery(Blog).where(Blog.user == None)
        self.assertWhere(sq, '("blog"."user_id" IS ?)', [None])

        sq = SelectQuery(Blog).where(Blog.user != None)
        self.assertWhere(sq, '("blog"."user_id" IS NOT ?)', [None])

        sq = SelectQuery(Blog).where(~(Blog.user == None))
        self.assertWhere(sq, 'NOT ("blog"."user_id" IS ?)', [None])

    def test_is_null(self):
        sq = SelectQuery(Blog).where(Blog.user.is_null())
        self.assertWhere(sq, '("blog"."user_id" IS ?)', [None])

        sq = SelectQuery(Blog).where(Blog.user.is_null(False))
        self.assertWhere(sq, '("blog"."user_id" IS NOT ?)', [None])

        sq = SelectQuery(Blog).where(~(Blog.user.is_null()))
        self.assertWhere(sq, 'NOT ("blog"."user_id" IS ?)', [None])

        sq = SelectQuery(Blog).where(~(Blog.user.is_null(False)))
        self.assertWhere(sq, 'NOT ("blog"."user_id" IS NOT ?)', [None])

    def test_where_coercion(self):
        sq = SelectQuery(User).where(User.id < '5')
        self.assertWhere(sq, '("users"."id" < ?)', [5])

        sq = SelectQuery(User).where(User.id < (User.id - '5'))
        self.assertWhere(sq, '("users"."id" < ("users"."id" - ?))', [5])

    def test_where_lists(self):
        sq = SelectQuery(User).where(User.username << ['u1', 'u2'])
        self.assertWhere(sq, '("users"."username" IN (?, ?))', ['u1', 'u2'])

        sq = SelectQuery(User).where(User.username.in_(('u1', 'u2')))
        self.assertWhere(sq, '("users"."username" IN (?, ?))', ['u1', 'u2'])

        sq = SelectQuery(User).where(User.username.not_in(['u1', 'u2']))
        self.assertWhere(sq, '("users"."username" NOT IN (?, ?))', ['u1', 'u2'])

        sq = SelectQuery(User).where((User.username << ['u1', 'u2']) | (User.username << ['u3', 'u4']))
        self.assertWhere(sq, '(("users"."username" IN (?, ?)) OR ("users"."username" IN (?, ?)))', ['u1', 'u2', 'u3', 'u4'])

    def test_where_in_empty(self):
        sq = SelectQuery(User).where(User.username << [])
        self.assertWhere(sq, '(0 = 1)', [])

        sq = SelectQuery(User).where(User.username << ())
        self.assertWhere(sq, '(0 = 1)', [])

        # NOT IN is not affected.
        sq = SelectQuery(User).where(User.username.not_in([]))
        self.assertWhere(sq, '("users"."username" NOT IN ())', [])

        # But ~ (x IN y) is.
        sq = SelectQuery(User).where(~(User.username << ()))
        self.assertWhere(sq, 'NOT (0 = 1)', [])

    def test_where_sets(self):
        def where_sql(expr, query=None):
            if query is None:
                query = User.select()
            query = query.where(expr)
            return self.parse_query(query, query._where)

        sql, params = where_sql(User.username << set(['u1', 'u2']))
        self.assertEqual(sql, '("users"."username" IN (?, ?))')
        self.assertTrue(isinstance(params, list))
        self.assertEqual(sorted(params), ['u1', 'u2'])

        sql, params = where_sql(User.username.in_(set(['u1', 'u2'])))
        self.assertEqual(sql, '("users"."username" IN (?, ?))')
        self.assertEqual(sorted(params), ['u1', 'u2'])

    def test_where_joins(self):
        sq = SelectQuery(User).where(
            ((User.id == 1) | (User.id == 2)) &
            ((Blog.pk == 3) | (Blog.pk == 4))
        ).where(User.id == 5).join(Blog)
        self.assertWhere(sq, '(((("users"."id" = ?) OR ("users"."id" = ?)) AND (("blog"."pk" = ?) OR ("blog"."pk" = ?))) AND ("users"."id" = ?))', [1, 2, 3, 4, 5])

    def test_where_join_non_pk_fk(self):
        sq = (SelectQuery(Package)
              .join(PackageItem)
              .where(PackageItem.title == 'p1'))
        self.assertWhere(sq, '("packageitem"."title" = ?)', ['p1'])

        sq = (SelectQuery(PackageItem)
              .join(Package)
              .where(Package.barcode == 'b1'))
        self.assertWhere(sq, '("package"."barcode" = ?)', ['b1'])

    def test_where_functions(self):
        sq = SelectQuery(User).where(fn.Lower(fn.Substr(User.username, 0, 1)) == 'a')
        self.assertWhere(sq, '(Lower(Substr("users"."username", ?, ?)) = ?)', [0, 1, 'a'])

    def test_where_conversion(self):
        sq = SelectQuery(CSVRow).where(CSVRow.data == Param(['foo', 'bar']))
        self.assertWhere(sq, '("csvrow"."data" = ?)', ['foo,bar'])

        sq = SelectQuery(CSVRow).where(
            CSVRow.data == fn.FOO(Param(['foo', 'bar'])))
        self.assertWhere(sq, '("csvrow"."data" = FOO(?))', ['foo,bar'])

        sq = SelectQuery(CSVRow).where(
            CSVRow.data == fn.FOO(Param(['foo', 'bar'])).coerce(False))
        self.assertWhere(sq, '("csvrow"."data" = FOO(?))', [['foo', 'bar']])

    def test_where_clauses(self):
        sq = SelectQuery(Blog).where(
            Blog.pub_date < (fn.NOW() - SQL('INTERVAL 1 HOUR')))
        self.assertWhere(sq, '("blog"."pub_date" < (NOW() - INTERVAL 1 HOUR))', [])

    def test_where_r(self):
        sq = SelectQuery(Blog).where(Blog.pub_date < R('NOW() - INTERVAL 1 HOUR'))
        self.assertWhere(sq, '("blog"."pub_date" < NOW() - INTERVAL 1 HOUR)', [])

        sq = SelectQuery(Blog).where(Blog.pub_date < (fn.Now() - R('INTERVAL 1 HOUR')))
        self.assertWhere(sq, '("blog"."pub_date" < (Now() - INTERVAL 1 HOUR))', [])

    def test_where_subqueries(self):
        sq = SelectQuery(User).where(User.id << User.select().where(User.username=='u1'))
        self.assertWhere(sq, '("users"."id" IN (SELECT "users"."id" FROM "users" AS users WHERE ("users"."username" = ?)))', ['u1'])

        sq = SelectQuery(User).where(User.username << User.select(User.username).where(User.username=='u1'))
        self.assertWhere(sq, '("users"."username" IN (SELECT "users"."username" FROM "users" AS users WHERE ("users"."username" = ?)))', ['u1'])

        sq = SelectQuery(Blog).where((Blog.pk == 3) | (Blog.user << User.select().where(User.username << ['u1', 'u2'])))
        self.assertWhere(sq, '(("blog"."pk" = ?) OR ("blog"."user_id" IN (SELECT "users"."id" FROM "users" AS users WHERE ("users"."username" IN (?, ?)))))', [3, 'u1', 'u2'])

    def test_where_fk(self):
        sq = SelectQuery(Blog).where(Blog.user == User(id=100))
        self.assertWhere(sq, '("blog"."user_id" = ?)', [100])

        sq = SelectQuery(Blog).where(Blog.user << [User(id=100), User(id=101)])
        self.assertWhere(sq, '("blog"."user_id" IN (?, ?))', [100, 101])

        sq = SelectQuery(PackageItem).where(PackageItem.package == Package(barcode='b1'))
        self.assertWhere(sq, '("packageitem"."package_id" = ?)', ['b1'])

    def test_where_negation(self):
        sq = SelectQuery(Blog).where(~(Blog.title == 'foo'))
        self.assertWhere(sq, 'NOT ("blog"."title" = ?)', ['foo'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') | (Blog.title == 'bar')))
        self.assertWhere(sq, 'NOT (("blog"."title" = ?) OR ("blog"."title" = ?))', ['foo', 'bar'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & (Blog.title == 'baz'))
        self.assertWhere(sq, '(NOT (("blog"."title" = ?) AND ("blog"."title" = ?)) AND ("blog"."title" = ?))', ['foo', 'bar', 'baz'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & ((Blog.title == 'baz') & (Blog.title == 'fizz')))
        self.assertWhere(sq, '(NOT (("blog"."title" = ?) AND ("blog"."title" = ?)) AND (("blog"."title" = ?) AND ("blog"."title" = ?)))', ['foo', 'bar', 'baz', 'fizz'])

    def test_where_negation_single_clause(self):
        sq = SelectQuery(Blog).where(~Blog.title)
        self.assertWhere(sq, 'NOT "blog"."title"', [])

        sq = sq.where(Blog.pk > 1)
        self.assertWhere(sq, '(NOT "blog"."title" AND ("blog"."pk" > ?))', [1])

    def test_where_chaining_collapsing(self):
        sq = SelectQuery(User).where(User.id == 1).where(User.id == 2).where(User.id == 3)
        self.assertWhere(sq, '((("users"."id" = ?) AND ("users"."id" = ?)) AND ("users"."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) & (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, '((("users"."id" = ?) AND ("users"."id" = ?)) AND ("users"."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) | (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, '((("users"."id" = ?) OR ("users"."id" = ?)) AND ("users"."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) & (User.id == 3))
        self.assertWhere(sq, '(("users"."id" = ?) AND (("users"."id" = ?) AND ("users"."id" = ?)))', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) | (User.id == 3))
        self.assertWhere(sq, '(("users"."id" = ?) AND (("users"."id" = ?) OR ("users"."id" = ?)))', [1, 2, 3])

        sq = SelectQuery(User).where(~(User.id == 1)).where(User.id == 2).where(~(User.id == 3))
        self.assertWhere(sq, '((NOT ("users"."id" = ?) AND ("users"."id" = ?)) AND NOT ("users"."id" = ?))', [1, 2, 3])

    def test_tuples(self):
        sq = User.select().where(Tuple(User.id, User.username) == (1, 'hello'))
        self.assertWhere(sq, '(("users"."id", "users"."username") = (?, ?))', [1, 'hello'])

    def test_grouping(self):
        sq = SelectQuery(User).group_by(User.id)
        self.assertGroupBy(sq, '"users"."id"', [])

        sq = SelectQuery(User).group_by(User)
        self.assertGroupBy(sq, '"users"."id", "users"."username"', [])

    def test_having(self):
        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            fn.Count(Blog.pk) > 2
        )
        self.assertHaving(sq, '(Count("blog"."pk") > ?)', [2])

        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            (fn.Count(Blog.pk) > 10) | (fn.Count(Blog.pk) < 2)
        )
        self.assertHaving(sq, '((Count("blog"."pk") > ?) OR (Count("blog"."pk") < ?))', [10, 2])

    def test_ordering(self):
        sq = SelectQuery(User).join(Blog).order_by(Blog.title)
        self.assertOrderBy(sq, '"blog"."title"', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.asc())
        self.assertOrderBy(sq, '"blog"."title" ASC', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.desc())
        self.assertOrderBy(sq, '"blog"."title" DESC', [])

        sq = SelectQuery(User).join(Blog).order_by(User.username.desc(), Blog.title.asc())
        self.assertOrderBy(sq, '"users"."username" DESC, "blog"."title" ASC', [])

        base_sq = SelectQuery(User, User.username, fn.Count(Blog.pk).alias('count')).join(Blog).group_by(User.username)
        sq = base_sq.order_by(fn.Count(Blog.pk).desc())
        self.assertOrderBy(sq, 'Count("blog"."pk") DESC', [])

        sq = base_sq.order_by(R('count'))
        self.assertOrderBy(sq, 'count', [])

        sq = OrderedModel.select()
        self.assertOrderBy(sq, '"orderedmodel"."created" DESC', [])

        sq = OrderedModel.select().order_by(OrderedModel.id.asc())
        self.assertOrderBy(sq, '"orderedmodel"."id" ASC', [])

        sq = User.select().order_by(User.id * 5)
        self.assertOrderBy(sq, '("users"."id" * ?)', [5])
        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username" '
            'FROM "users" AS users ORDER BY ("users"."id" * ?)',
            [5]))

    def test_ordering_extend(self):
        sq = User.select().order_by(User.username, extend=True)
        self.assertEqual([f.name for f in sq._order_by], ['username'])

        sq = sq.order_by(User.id.desc(), extend=True)
        self.assertEqual([f.name for f in sq._order_by], ['username', 'id'])

        sq = sq.order_by(extend=True)
        self.assertEqual([f.name for f in sq._order_by], ['username', 'id'])

        sq = sq.order_by()
        self.assertTrue(sq._order_by is None)

        sq = sq.order_by(extend=True)
        self.assertTrue(sq._order_by is None)

        self.assertRaises(ValueError, lambda: sq.order_by(foo=True))

    def test_ordering_sugar(self):
        sq = User.select().order_by(-User.username)
        self.assertOrderBy(sq, '"users"."username" DESC', [])

        sq = User.select().order_by(+User.username)
        self.assertOrderBy(sq, '"users"."username" ASC', [])

        sq = User.select().join(Blog).order_by(
            +User.username,
            -Blog.title)
        self.assertOrderBy(
            sq,
            '"users"."username" ASC, "blog"."title" DESC',
            [])

    def test_from_subquery(self):
        # e.g. annotate the number of blogs per user, then annotate the number
        # of users with that number of blogs.
        inner = (Blog
                 .select(fn.COUNT(Blog.pk).alias('blog_ct'))
                 .group_by(Blog.user))
        blog_ct = SQL('blog_ct')
        outer = (Blog
                 .select(blog_ct, fn.COUNT(blog_ct).alias('blog_ct_n'))
                 .from_(inner)
                 .group_by(blog_ct))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT blog_ct, COUNT(blog_ct) AS blog_ct_n '
            'FROM ('
            'SELECT COUNT("blog"."pk") AS blog_ct FROM "blog" AS blog '
            'GROUP BY "blog"."user_id") '
            'GROUP BY blog_ct'))

    def test_from_multiple(self):
        q = (User
             .select()
             .from_(User, Blog)
             .where(Blog.user == User.id))

        sql, params = compiler.generate_select(q)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username" '
            'FROM "users" AS users, "blog" AS blog '
            'WHERE ("blog"."user_id" = "users"."id")'))

        q = (User
             .select()
             .from_(User, Blog, Comment)
             .where(
                 (Blog.user == User.id) &
                 (Comment.blog == Blog.pk)))

        sql, params = compiler.generate_select(q)
        self.assertEqual(sql, (
            'SELECT "users"."id", "users"."username" '
            'FROM "users" AS users, "blog" AS blog, "comment" AS comment '
            'WHERE (("blog"."user_id" = "users"."id") AND '
            '("comment"."blog_id" = "blog"."pk"))'))

    def test_paginate(self):
        sq = SelectQuery(User).paginate(1, 20)
        self.assertEqual(sq._limit, 20)
        self.assertEqual(sq._offset, 0)

        sq = SelectQuery(User).paginate(3, 30)
        self.assertEqual(sq._limit, 30)
        self.assertEqual(sq._offset, 60)

    def test_limit(self):
        orig = User._meta.database.limit_max
        User._meta.database.limit_max = -1
        try:
            sq = SelectQuery(User, User.id).limit(10).offset(5)
            sql, params = compiler.generate_select(sq)
            self.assertEqual(sql, (
                'SELECT "users"."id" FROM "users" AS users LIMIT 10 OFFSET 5'))

            sq = SelectQuery(User, User.id).offset(5)
            sql, params = compiler.generate_select(sq)
            self.assertEqual(sql, (
                'SELECT "users"."id" FROM "users" AS users LIMIT -1 OFFSET 5'))

            sq = SelectQuery(User, User.id).limit(0).offset(0)
            sql, params = compiler.generate_select(sq)
            self.assertEqual(sql, (
                'SELECT "users"."id" FROM "users" AS users LIMIT 0 OFFSET 0'))
        finally:
            User._meta.database.limit_max = orig

    def test_prefetch_subquery(self):
        sq = SelectQuery(User).where(User.username == 'foo')
        sq2 = SelectQuery(Blog).where(Blog.title == 'bar')
        sq3 = SelectQuery(Comment).where(Comment.comment == 'baz')
        fixed = prefetch_add_subquery(sq, (sq2, sq3))
        fixed_sql = [
            ('SELECT "t1"."id", "t1"."username" FROM "users" AS t1 WHERE ("t1"."username" = ?)', ['foo']),
            ('SELECT "t1"."pk", "t1"."user_id", "t1"."title", "t1"."content", "t1"."pub_date" FROM "blog" AS t1 WHERE (("t1"."title" = ?) AND ("t1"."user_id" IN (SELECT "t2"."id" FROM "users" AS t2 WHERE ("t2"."username" = ?))))', ['bar', 'foo']),
            ('SELECT "t1"."id", "t1"."blog_id", "t1"."comment" FROM "comment" AS t1 WHERE (("t1"."comment" = ?) AND ("t1"."blog_id" IN (SELECT "t2"."pk" FROM "blog" AS t2 WHERE (("t2"."title" = ?) AND ("t2"."user_id" IN (SELECT "t3"."id" FROM "users" AS t3 WHERE ("t3"."username" = ?)))))))', ['baz', 'bar', 'foo']),
        ]
        for prefetch_result, expected in zip(fixed, fixed_sql):
            self.assertEqual(
                normal_compiler.generate_select(prefetch_result.query),
                expected)

        fixed = prefetch_add_subquery(sq, (Blog,))
        fixed_sql = [
            ('SELECT "t1"."id", "t1"."username" FROM "users" AS t1 WHERE ("t1"."username" = ?)', ['foo']),
            ('SELECT "t1"."pk", "t1"."user_id", "t1"."title", "t1"."content", "t1"."pub_date" FROM "blog" AS t1 WHERE ("t1"."user_id" IN (SELECT "t2"."id" FROM "users" AS t2 WHERE ("t2"."username" = ?)))', ['foo']),
        ]
        for prefetch_result, expected in zip(fixed, fixed_sql):
            self.assertEqual(
                normal_compiler.generate_select(prefetch_result.query),
                expected)

    def test_prefetch_non_pk_fk(self):
        sq = SelectQuery(Package).where(Package.barcode % 'b%')
        sq2 = SelectQuery(PackageItem).where(PackageItem.title % 'n%')
        fixed = prefetch_add_subquery(sq, (sq2,))
        fixed_sq = (
            'SELECT "t1"."id", "t1"."barcode" FROM "package" AS t1 '
            'WHERE ("t1"."barcode" LIKE ?)',
            ['b%'])
        fixed_sq2 = (
            'SELECT "t1"."id", "t1"."title", "t1"."package_id" '
            'FROM "packageitem" AS t1 '
            'WHERE ('
            '("t1"."title" LIKE ?) AND '
            '("t1"."package_id" IN ('
            'SELECT "t2"."barcode" FROM "package" AS t2 '
            'WHERE ("t2"."barcode" LIKE ?))))',
            ['n%', 'b%'])
        fixed_sql = [fixed_sq, fixed_sq2]

        for prefetch_result, expected in zip(fixed, fixed_sql):
            self.assertEqual(
                normal_compiler.generate_select(prefetch_result.query),
                expected)

    def test_prefetch_subquery_same_depth(self):
        sq = Parent.select()
        sq2 = Child.select()
        sq3 = Orphan.select()
        sq4 = ChildPet.select()
        sq5 = OrphanPet.select()
        fixed = prefetch_add_subquery(sq, (sq2, sq3, sq4, sq5))
        fixed_sql = [
            ('SELECT "t1"."id", "t1"."data" FROM "parent" AS t1', []),
            ('SELECT "t1"."id", "t1"."parent_id", "t1"."data" FROM "child" AS t1 WHERE ("t1"."parent_id" IN (SELECT "t2"."id" FROM "parent" AS t2))', []),
            ('SELECT "t1"."id", "t1"."parent_id", "t1"."data" FROM "orphan" AS t1 WHERE ("t1"."parent_id" IN (SELECT "t2"."id" FROM "parent" AS t2))', []),
            ('SELECT "t1"."id", "t1"."child_id", "t1"."data" FROM "childpet" AS t1 WHERE ("t1"."child_id" IN (SELECT "t2"."id" FROM "child" AS t2 WHERE ("t2"."parent_id" IN (SELECT "t3"."id" FROM "parent" AS t3))))', []),
            ('SELECT "t1"."id", "t1"."orphan_id", "t1"."data" FROM "orphanpet" AS t1 WHERE ("t1"."orphan_id" IN (SELECT "t2"."id" FROM "orphan" AS t2 WHERE ("t2"."parent_id" IN (SELECT "t3"."id" FROM "parent" AS t3))))', []),
        ]
        for prefetch_result, expected in zip(fixed, fixed_sql):
            self.assertEqual(
                normal_compiler.generate_select(prefetch_result.query),
                expected)

    def test_outer_inner_alias(self):
        expected = ('SELECT "t1"."id", "t1"."username", '
                    '(SELECT Sum("t2"."id") FROM "users" AS t2 '
                    'WHERE ("t2"."id" = "t1"."id")) AS xxx FROM "users" AS t1')
        UA = User.alias()
        inner = SelectQuery(UA, fn.Sum(UA.id)).where(UA.id == User.id)
        query = User.select(User, inner.alias('xxx'))
        sql, _ = normal_compiler.generate_select(query)
        self.assertEqual(sql, expected)

        # Ensure that ModelAlias.select() does the right thing.
        inner = UA.select(fn.Sum(UA.id)).where(UA.id == User.id)
        query = User.select(User, inner.alias('xxx'))
        sql, _ = normal_compiler.generate_select(query)
        self.assertEqual(sql, expected)

    def test_parentheses_cleaning(self):
        query = (User
                 .select(
                     User.username,
                     fn.Count(
                         Blog
                         .select(Blog.pk)
                         .where(Blog.user == User.id)).alias('blog_ct')))
        sql, params = normal_compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "t1"."username", '
            'Count('
            'SELECT "t2"."pk" FROM "blog" AS t2 '
            'WHERE ("t2"."user_id" = "t1"."id")) AS blog_ct FROM "users" AS t1'))

        query = (User
                 .select(User.username)
                 .where(fn.Exists(fn.Exists(User.select(User.id)))))
        sql, params = normal_compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "t1"."username" FROM "users" AS t1 '
            'WHERE Exists(Exists('
            'SELECT "t2"."id" FROM "users" AS t2))'))

    def test_division(self):
        query = User.select(User.id / 2)
        self.assertSelect(query, '("users"."id" / ?)', [2])

    def test_select_from_alias(self):
        UA = User.alias()
        query = UA.select().where(UA.username == 'charlie')
        sql, params = normal_compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS t1 '
            'WHERE ("t1"."username" = ?)'))
        self.assertEqual(params, ['charlie'])

        q2 = query.join(User, on=(User.id == UA.id)).where(User.id == 2)
        sql, params = normal_compiler.generate_select(q2)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS t1 '
            'INNER JOIN "users" AS t2 '
            'ON ("t2"."id" = "t1"."id") '
            'WHERE (("t1"."username" = ?) AND ("t2"."id" = ?))'))
        self.assertEqual(params, ['charlie', 2])

class TestUpdateQuery(PeeweeTestCase):
    def setUp(self):
        super(TestUpdateQuery, self).setUp()
        self._orig_returning_clause = test_db.returning_clause

    def tearDown(self):
        super(TestUpdateQuery, self).tearDown()
        test_db.returning_clause = self._orig_returning_clause

    def test_update(self):
        uq = UpdateQuery(User, {User.username: 'updated'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = ?',
            ['updated']))

        uq = UpdateQuery(Blog, {Blog.user: User(id=100, username='foo')})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET "user_id" = ?',
            [100]))

        uq = UpdateQuery(User, {User.id: User.id + 5})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "id" = ("users"."id" + ?)',
            [5]))

        uq = UpdateQuery(User, {User.id: 5 * (3 + User.id)})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "id" = (? * (? + "users"."id"))',
            [5, 3]))

        # set username to the maximum id of all users -- silly, yes, but lets see what happens
        uq = UpdateQuery(User, {User.username: User.select(fn.Max(User.id).alias('maxid'))})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = (SELECT Max("users"."id") AS maxid '
            'FROM "users" AS users)',
            []))

        uq = UpdateQuery(Blog, {Blog.title: 'foo', Blog.content: 'bar'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET "title" = ?, "content" = ?',
            ['foo', 'bar']))

        pub_date = datetime.datetime(2014, 1, 2, 3, 4)
        uq = UpdateQuery(Blog, {
            Blog.title: 'foo',
            Blog.pub_date: pub_date,
            Blog.user: User(id=15),
            Blog.content: 'bar'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET '
            '"user_id" = ?, "title" = ?, "content" = ?, "pub_date" = ?',
            [15, 'foo', 'bar', pub_date]))

    def test_via_model(self):
        uq = User.update(username='updated')
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = ?',
            ['updated']))

        uq = User.update({User.username: 'updated'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = ?',
            ['updated']))

        uq = Blog.update({Blog.user: User(id=100)})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET "user_id" = ?',
            [100]))

        uq = User.update({User.id: User.id + 5})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "id" = ("users"."id" + ?)',
            [5]))

    def test_on_conflict(self):
        uq = UpdateQuery(User, {
            User.username: 'charlie'}).on_conflict('IGNORE')
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE OR IGNORE "users" SET "username" = ?',
            ['charlie']))

    def test_update_special(self):
        uq = UpdateQuery(CSVRow, {CSVRow.data: ['foo', 'bar', 'baz']})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "csvrow" SET "data" = ?',
            ['foo,bar,baz']))

        uq = UpdateQuery(CSVRow, {CSVRow.data: []})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "csvrow" SET "data" = ?',
            ['']))

    def test_where(self):
        uq = UpdateQuery(User, {User.username: 'updated'}).where(User.id == 2)
        self.assertWhere(uq, '("users"."id" = ?)', [2])

        uq = (UpdateQuery(User, {User.username: 'updated'})
              .where(User.id == 2)
              .where(User.username == 'old'))
        self.assertWhere(uq, '(("users"."id" = ?) AND ("users"."username" = ?))', [2, 'old'])

    def test_returning_clause(self):
        uq = UpdateQuery(User, {User.username: 'baze'}).where(User.id > 2)
        test_db.returning_clause = False
        self.assertRaises(ValueError, lambda: uq.returning(User.username))

        test_db.returning_clause = True
        uq_returning = uq.returning(User.username)

        self.assertFalse(id(uq_returning) == id(uq))
        self.assertIsNone(uq._returning)

        sql, params = normal_compiler.generate_update(uq_returning)
        self.assertEqual(sql, (
            'UPDATE "users" SET "username" = ? '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."username"'))
        self.assertEqual(params, ['baze', 2])

        uq2 = uq_returning.returning(User, SQL('1'))
        sql, params = normal_compiler.generate_update(uq2)
        self.assertEqual(sql, (
            'UPDATE "users" SET "username" = ? '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."id", "users"."username", 1'))
        self.assertEqual(params, ['baze', 2])

        uq_no_return = uq2.returning(None)
        sql, _ = normal_compiler.generate_update(uq_no_return)
        self.assertFalse('RETURNING' in sql)


class TestInsertQuery(PeeweeTestCase):
    def setUp(self):
        super(TestInsertQuery, self).setUp()
        self._orig_returning_clause = test_db.returning_clause

    def tearDown(self):
        super(TestInsertQuery, self).tearDown()
        test_db.returning_clause = self._orig_returning_clause

    def test_insert(self):
        iq = InsertQuery(User, {User.username: 'inserted'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['inserted']))

        iq = InsertQuery(User, {'username': 'inserted'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['inserted']))

        pub_date = datetime.datetime(2014, 1, 2, 3, 4)
        iq = InsertQuery(Blog, {
            Blog.title: 'foo',
            Blog.content: 'bar',
            Blog.pub_date: pub_date,
            Blog.user: User(id=10)})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "blog" ("user_id", "title", "content", "pub_date") '
            'VALUES (?, ?, ?, ?)',
            [10, 'foo', 'bar', pub_date]))

        subquery = Blog.select(Blog.title)
        iq = InsertQuery(User, fields=[User.username], query=subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'SELECT "t2"."title" FROM "blog" AS t2'))

        subquery = Blog.select(Blog.pk, Blog.title)
        iq = InsertQuery(User, query=subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" '
            'SELECT "t2"."pk", "t2"."title" FROM "blog" AS t2'))

    def test_insert_default_vals(self):
        class DM(TestModel):
            name = CharField(default='peewee')
            value = IntegerField(default=1, null=True)
            other = FloatField()

        iq = InsertQuery(DM)
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['peewee', 1]))

        iq = InsertQuery(DM, {'name': 'herman'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['herman', 1]))

        iq = InsertQuery(DM, {'value': None})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['peewee', None]))

        iq = InsertQuery(DM, {DM.name: 'huey', 'other': 2.0})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value", "other") VALUES (?, ?, ?)',
            ['huey', 1, 2.0]))

    def test_insert_default_callable(self):
        def default_fn():
            return -1

        class DM(TestModel):
            name = CharField()
            value = IntegerField(default=default_fn)

        iq = InsertQuery(DM, {DM.name: 'u1'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['u1', -1]))

        iq = InsertQuery(DM, {'name': 'u2', 'value': 1})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['u2', 1]))

    def test_insert_many(self):
        iq = InsertQuery(User, rows=[
            {'username': 'u1'},
            {User.username: 'u2'},
            {'username': 'u3'},
        ])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)',
            ['u1', 'u2', 'u3']))

        iq = InsertQuery(User, rows=[{'username': 'u1'}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['u1']))

        iq = InsertQuery(User, rows=[])
        if isinstance(test_db, MySQLDatabase):
            self.assertEqual(compiler.generate_insert(iq), (
                'INSERT INTO "users" ("users"."id") VALUES (DEFAULT)', []))
        else:
            self.assertEqual(compiler.generate_insert(iq), (
                'INSERT INTO "users" DEFAULT VALUES', []))

    def test_insert_many_defaults(self):
        class DefaultGenerator(object):
            def __init__(self):
                self.i = 0

            def __call__(self):
                self.i += 1
                return self.i

        default_gen = DefaultGenerator()

        class DM(TestModel):
            cd = IntegerField(default=default_gen)
            pd = IntegerField(default=-1)
            name = CharField()

        iq = InsertQuery(DM, rows=[{'name': 'u1'}, {'name': 'u2'}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("cd", "pd", "name") VALUES '
            '(?, ?, ?), (?, ?, ?)',
            [1, -1, 'u1', 2, -1, 'u2']))

        iq = InsertQuery(DM, rows=[
            {DM.name: 'u3', DM.cd: 99},
            {DM.name: 'u4', DM.pd: -2},
            {DM.name: 'u5'}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("cd", "pd", "name") VALUES '
            '(?, ?, ?), (?, ?, ?), (?, ?, ?)',
            [99, -1, 'u3', 3, -2, 'u4', 4, -1, 'u5']))

    def test_insert_many_gen(self):
        def row_generator():
            for i in range(3):
                yield {'username': 'u%s' % i}

        iq = InsertQuery(User, rows=row_generator())
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)',
            ['u0', 'u1', 'u2']))

    def test_insert_special(self):
        iq = InsertQuery(CSVRow, {CSVRow.data: ['foo', 'bar', 'baz']})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?)',
            ['foo,bar,baz']))

        iq = InsertQuery(CSVRow, {CSVRow.data: []})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?)',
            ['']))

        iq = InsertQuery(CSVRow, rows=[
            {CSVRow.data: ['foo', 'bar', 'baz']},
            {CSVRow.data: ['a', 'b']},
            {CSVRow.data: ['b']},
            {CSVRow.data: []}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?), (?), (?), (?)',
            ['foo,bar,baz', 'a,b', 'b', '']))

    def test_empty_insert(self):
        class EmptyModel(TestModel):
            pass
        iq = InsertQuery(EmptyModel, {})
        sql, params = compiler.generate_insert(iq)
        if isinstance(test_db, MySQLDatabase):
            self.assertEqual(sql, (
                'INSERT INTO "emptymodel" ("emptymodel"."id") '
                'VALUES (DEFAULT)'))
        else:
            self.assertEqual(sql, 'INSERT INTO "emptymodel" DEFAULT VALUES')

    def test_upsert(self):
        class TestUser(User):
            class Meta:
                database = SqliteDatabase(':memory:')
        sql, params = TestUser.insert(username='charlie').upsert().sql()
        self.assertEqual(sql, (
            'INSERT OR REPLACE INTO "testuser" ("username") VALUES (?)'))
        self.assertEqual(params, ['charlie'])

    def test_on_conflict(self):
        class TestUser(User):
            class Meta:
                database = SqliteDatabase(':memory:')
        sql, params = TestUser.insert(username='huey').on_conflict('IGNORE').sql()
        self.assertEqual(sql, (
            'INSERT OR IGNORE INTO "testuser" ("username") VALUES (?)'))
        self.assertEqual(params, ['huey'])

    def test_upsert_mysql(self):
        class TestUser(User):
            class Meta:
                database = MySQLDatabase('peewee_test')

        query = TestUser.insert(username='zaizee', id=3).upsert()
        sql, params = query.sql()
        self.assertEqual(sql, (
            'REPLACE INTO `testuser` (`id`, `username`) VALUES (%s, %s)'))
        self.assertEqual(params, [3, 'zaizee'])

    def test_returning(self):
        iq = User.insert(username='huey')
        test_db.returning_clause = False
        self.assertRaises(ValueError, lambda: iq.returning(User.id))

        test_db.returning_clause = True
        iq_returning = iq.returning(User.id)

        self.assertFalse(id(iq_returning) == id(iq))
        self.assertIsNone(iq._returning)

        sql, params = normal_compiler.generate_insert(iq_returning)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "users"."id"'))
        self.assertEqual(params, ['huey'])

        iq2 = iq_returning.returning(User, SQL('1'))
        sql, params = normal_compiler.generate_insert(iq2)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "users"."id", "users"."username", 1'))
        self.assertEqual(params, ['huey'])

        iq_no_return = iq2.returning(None)
        sql, _ = normal_compiler.generate_insert(iq_no_return)
        self.assertFalse('RETURNING' in sql)


class TestInsertReturning(PeeweeTestCase):
    def setUp(self):
        super(TestInsertReturning, self).setUp()

        class TestReturningDatabase(TestDatabase):
            insert_returning = True

        db = TestReturningDatabase(':memory:')
        self.rc = db.compiler()

        class BaseModel(TestModel):
            class Meta:
                database = db

        self.BaseModel = BaseModel

    def assertInsertSQL(self, insert_query, sql, params=None):
        qsql, qparams = self.rc.generate_insert(insert_query)
        self.assertEqual(qsql, sql)
        self.assertEqual(qparams, params or [])

    def test_insert_returning(self):
        class User(self.BaseModel):
            username = CharField()

        self.assertInsertSQL(
            User.insert(username='charlie'),
            'INSERT INTO "user" ("username") VALUES (?) RETURNING "id"',
            ['charlie'])

    def test_insert_non_int_pk(self):
        class User(self.BaseModel):
            username = CharField(primary_key=True)
            data = TextField(default='')

        self.assertInsertSQL(
            User.insert(username='charlie'),
            ('INSERT INTO "user" ("username", "data") '
             'VALUES (?, ?) RETURNING "username"'),
            ['charlie', ''])

    def test_insert_composite_key(self):
        class Person(self.BaseModel):
            first = CharField()
            last = CharField()
            dob = DateField()
            email = CharField()

            class Meta:
                primary_key = CompositeKey('first', 'last', 'dob')

        self.assertInsertSQL(
            Person.insert(
                first='huey',
                last='leifer',
                dob='05/01/2011',
                email='huey@kitties.cat'),
            ('INSERT INTO "person" '
             '("first", "last", "dob", "email") '
             'VALUES (?, ?, ?, ?) '
             'RETURNING "first", "last", "dob"'),
            ['huey', 'leifer', '05/01/2011', 'huey@kitties.cat'])

    def test_insert_many(self):
        class User(self.BaseModel):
            username = CharField()

        data = [{'username': 'user-%s' % i} for i in range(3)]
        # Bulk inserts do not ask for returned primary keys.
        self.assertInsertSQL(
            User.insert_many(data),
            'INSERT INTO "user" ("username") VALUES (?), (?), (?)',
            ['user-0', 'user-1', 'user-2'])


class TestDeleteQuery(PeeweeTestCase):
    def setUp(self):
        super(TestDeleteQuery, self).setUp()
        self._orig_returning_clause = test_db.returning_clause

    def tearDown(self):
        super(TestDeleteQuery, self).tearDown()
        test_db.returning_clause = self._orig_returning_clause

    def test_returning(self):
        dq = DeleteQuery(User).where(User.id > 2)
        test_db.returning_clause = False
        self.assertRaises(ValueError, lambda: dq.returning(User.username))

        test_db.returning_clause = True
        dq_returning = dq.returning(User.username)

        self.assertFalse(id(dq_returning) == id(dq))
        self.assertIsNone(dq._returning)

        sql, params = normal_compiler.generate_delete(dq_returning)
        self.assertEqual(sql, (
            'DELETE FROM "users" '
            'WHERE ("id" > ?) '
            'RETURNING "username"'))
        self.assertEqual(params, [2])

        dq2 = dq_returning.returning(User, SQL('1'))
        sql, params = normal_compiler.generate_delete(dq2)
        self.assertEqual(sql, (
            'DELETE FROM "users" WHERE ("id" > ?) '
            'RETURNING "id", "username", 1'))
        self.assertEqual(params, [2])

        dq_no_return = dq2.returning(None)
        sql, _ = normal_compiler.generate_delete(dq_no_return)
        self.assertFalse('RETURNING' in sql)

    def test_where(self):
        dq = DeleteQuery(User).where(User.id == 2)
        self.assertWhere(dq, '("users"."id" = ?)', [2])

        dq = (DeleteQuery(User)
              .where(User.id == 2)
              .where(User.username == 'old'))
        self.assertWhere(dq, '(("users"."id" = ?) AND ("users"."username" = ?))', [2, 'old'])

class TestRawQuery(PeeweeTestCase):
    def test_raw(self):
        q = 'SELECT * FROM "users" WHERE id=?'
        rq = RawQuery(User, q, 100)
        self.assertEqual(rq.sql(), (q, [100]))

class TestSchema(PeeweeTestCase):
    def test_schema(self):
        class WithSchema(TestModel):
            data = CharField()
            class Meta:
                schema = 'huey'
        query = WithSchema.select().where(WithSchema.data == 'mickey')
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "withschema"."id", "withschema"."data" FROM '
            '"huey"."withschema" AS withschema '
            'WHERE ("withschema"."data" = ?)'))

class TestDjangoFilters(PeeweeTestCase):
    # test things like filter, annotate, aggregate
    def test_filter(self):
        sq = User.filter(username='u1')
        self.assertJoins(sq, [])
        self.assertWhere(sq, '("users"."username" = ?)', ['u1'])

        sq = Blog.filter(user__username='u1')
        self.assertJoins(sq, ['INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")'])
        self.assertWhere(sq, '("users"."username" = ?)', ['u1'])

        sq = Blog.filter(user__username__in=['u1', 'u2'], comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")',
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])
        self.assertWhere(sq, '(("comment"."comment" = ?) AND ("users"."username" IN (?, ?)))', ['hurp', 'u1', 'u2'])

        sq = Blog.filter(user__username__in=['u1', 'u2']).filter(comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")',
        ])
        self.assertWhere(sq, '(("users"."username" IN (?, ?)) AND ("comment"."comment" = ?))', ['u1', 'u2', 'hurp'])

    def test_filter_dq(self):
        sq = User.filter(~DQ(username='u1'))
        self.assertWhere(sq, 'NOT ("users"."username" = ?)', ['u1'])

        sq = User.filter(DQ(username='u1') | DQ(username='u2'))
        self.assertJoins(sq, [])
        self.assertWhere(sq, '(("users"."username" = ?) OR ("users"."username" = ?))', ['u1', 'u2'])

        sq = Comment.filter(DQ(blog__user__username='u1') | DQ(blog__title='b1'), DQ(comment='c1'))
        self.assertJoins(sq, [
            'INNER JOIN "blog" AS blog ON ("comment"."blog_id" = "blog"."pk")',
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])
        self.assertWhere(sq, '((("users"."username" = ?) OR ("blog"."title" = ?)) AND ("comment"."comment" = ?))', ['u1', 'b1', 'c1'])

        sq = Blog.filter(DQ(user__username='u1') | DQ(comments__comment='c1'))
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON ("blog"."pk" = "comment"."blog_id")',
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])
        self.assertWhere(sq, '(("users"."username" = ?) OR ("comment"."comment" = ?))', ['u1', 'c1'])

        sq = Blog.filter(~DQ(user__username='u1') | DQ(user__username='b2'))
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])
        self.assertWhere(sq, '(NOT ("users"."username" = ?) OR ("users"."username" = ?))', ['u1', 'b2'])

        sq = Blog.filter(~(
            DQ(user__username='u1') |
            ~DQ(title='b1', pk=3)))
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON ("blog"."user_id" = "users"."id")',
        ])
        self.assertWhere(sq, 'NOT (("users"."username" = ?) OR NOT (("blog"."pk" = ?) AND ("blog"."title" = ?)))', ['u1', 3, 'b1'])

    def test_annotate(self):
        sq = User.select().annotate(Blog)
        self.assertSelect(sq, '"users"."id", "users"."username", Count("blog"."pk") AS count', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, '"users"."id", "users"."username"', [])

        sq = User.select(User.username).annotate(Blog, fn.Sum(Blog.pk).alias('sum')).where(User.username == 'foo')
        self.assertSelect(sq, '"users"."username", Sum("blog"."pk") AS sum', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])
        self.assertWhere(sq, '("users"."username" = ?)', ['foo'])
        self.assertGroupBy(sq, '"users"."username"', [])

        sq = User.select(User.username).annotate(Blog).annotate(Blog, fn.Max(Blog.pk).alias('mx'))
        self.assertSelect(sq, '"users"."username", Count("blog"."pk") AS count, Max("blog"."pk") AS mx', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, '"users"."username"', [])

        sq = User.select().annotate(Blog).order_by(R('count DESC'))
        self.assertSelect(sq, '"users"."id", "users"."username", Count("blog"."pk") AS count', [])
        self.assertOrderBy(sq, 'count DESC', [])

        sq = User.select().join(Blog, JOIN.LEFT_OUTER).switch(User).annotate(Blog)
        self.assertSelect(sq, '"users"."id", "users"."username", Count("blog"."pk") AS count', [])
        self.assertJoins(sq, ['LEFT OUTER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, '"users"."id", "users"."username"', [])

        sq = User.select().join(Blog, JOIN.LEFT_OUTER).annotate(Blog)
        self.assertSelect(sq, '"users"."id", "users"."username", Count("blog"."pk") AS count', [])
        self.assertJoins(sq, ['LEFT OUTER JOIN "blog" AS blog ON ("users"."id" = "blog"."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, '"users"."id", "users"."username"', [])

    def test_aggregate(self):
        sq = User.select().where(User.id < 10)._aggregate()
        self.assertSelect(sq, 'Count(*)', [])
        self.assertWhere(sq, '("users"."id" < ?)', [10])

        sq = User.select()._aggregate(fn.Sum(User.id).alias('baz'))
        self.assertSelect(sq, 'Sum("users"."id") AS baz', [])


class TestQueryCompiler(PeeweeTestCase):
    def test_clause(self):
        expr = fn.extract(Clause('year', R('FROM'), Blog.pub_date))
        sql, params = compiler.parse_node(expr)
        self.assertEqual(sql, 'extract(? FROM "pub_date")')
        self.assertEqual(params, ['year'])

    def test_custom_alias(self):
        class Person(TestModel):
            name = CharField()

            class Meta:
                table_alias = 'person_tbl'

        class Pet(TestModel):
            name = CharField()
            owner = ForeignKeyField(Person)

            class Meta:
                table_alias = 'pet_tbl'

        sq = Person.select().where(Person.name == 'peewee')
        sql = normal_compiler.generate_select(sq)
        self.assertEqual(
            sql[0],
            'SELECT "person_tbl"."id", "person_tbl"."name" FROM "person" AS '
            'person_tbl WHERE ("person_tbl"."name" = ?)')

        sq = Pet.select(Pet, Person.name).join(Person)
        sql = normal_compiler.generate_select(sq)
        self.assertEqual(
            sql[0],
            'SELECT "pet_tbl"."id", "pet_tbl"."name", "pet_tbl"."owner_id", '
            '"person_tbl"."name" '
            'FROM "pet" AS pet_tbl '
            'INNER JOIN "person" AS person_tbl '
            'ON ("pet_tbl"."owner_id" = "person_tbl"."id")')

    def test_alias_map(self):
        class A(TestModel):
            a = CharField()
            class Meta:
                table_alias = 'a_tbl'
        class B(TestModel):
            b = CharField()
            a_link = ForeignKeyField(A)
        class C(TestModel):
            c = CharField()
            b_link = ForeignKeyField(B)
        class D(TestModel):
            d = CharField()
            c_link = ForeignKeyField(C)
            class Meta:
                table_alias = 'd_tbl'

        sq = (D
              .select(D.d, C.c)
              .join(C)
              .where(C.b_link << (
                  B.select(B.id).join(A).where(A.a == 'a'))))
        sql, params = normal_compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT "d_tbl"."d", "t2"."c" '
            'FROM "d" AS d_tbl '
            'INNER JOIN "c" AS t2 ON ("d_tbl"."c_link_id" = "t2"."id") '
            'WHERE ("t2"."b_link_id" IN ('
            'SELECT "t3"."id" FROM "b" AS t3 '
            'INNER JOIN "a" AS a_tbl ON ("t3"."a_link_id" = "a_tbl"."id") '
            'WHERE ("a_tbl"."a" = ?)))'))

    def test_fn_no_coerce(self):
        class A(TestModel):
            i = IntegerField()
            d = DateTimeField()

        query = A.select(A.id).where(A.d == '2013-01-02')
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "a"."id" FROM "a" AS a WHERE ("a"."d" = ?)'))
        self.assertEqual(params, ['2013-01-02'])

        query = A.select(A.id).where(A.i == fn.Foo('test'))
        self.assertRaises(ValueError, query.sql)

        query = A.select(A.id).where(A.i == fn.Foo('test').coerce(False))
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT "a"."id" FROM "a" AS a WHERE ("a"."i" = Foo(?))'))
        self.assertEqual(params, ['test'])

    def test_strip_parentheses(self):
        tests = (
            ('x = 1', 'x = 1'),
            ('(x = 1)', 'x = 1'),
            ('(((((x = 1)))))', 'x = 1'),
            ('(((((x = (1))))))', 'x = (1)'),
            ('(((((x) = 1))))', '(x) = 1'),
            ('(x = (y = 2))', 'x = (y = 2)'),
            ('(((x = 1)', '((x = 1'),
            ('(x = 1)))', '(x = 1)))'),
            ('x = 1))', 'x = 1))'),
            ('((x = 1', '((x = 1'),
            ('(((()))', '('),
            ('((())))', ')'),
            ('', ''),
            ('(((())))', ''),
            ('((x), ((x) y))', '(x), ((x) y)'),
            ('(F(x) x), F(x)', '(F(x) x), F(x)'),
            ('((F(x) x) x), (F(x) F(x))', '((F(x) x) x), (F(x) F(x))'),
            ('(((F(x) x) x), (F(x) F(x)))', '((F(x) x) x), (F(x) F(x))'),
            ('((((F(x) x) x), (F(x) F(x))))', '((F(x) x) x), (F(x) F(x))'),
        )
        for s, expected in tests:
            self.assertEqual(strip_parens(s), expected)

    def test_parens_in_queries(self):
        query = User.select(
            fn.MAX(
                fn.IFNULL(1, 10) * 151,
                fn.IFNULL(None, 10)))
        self.assertSelect(
            query,
            'MAX((IFNULL(?, ?) * ?), IFNULL(?, ?))',
            [1, 10, 151, None, 10])


class TestValidation(PeeweeTestCase):
    def test_foreign_key_validation(self):
        def declare_bad(val):
            class Bad(TestModel):
                name = ForeignKeyField(val)

        vals_to_try = [
            ForeignKeyField(User),
            'Self',
            object,
            object()]

        for val in vals_to_try:
            self.assertRaises(TypeError, declare_bad, val)

    def test_backref_conflicts(self):
        class Note(TestModel):
            pass

        def declare_bad(related_name=None, backrefs=True):
            class Backref(Model):
                note = ForeignKeyField(Note, related_name=related_name)

                class Meta:
                    validate_backrefs = backrefs

        # First call succeeds since related_name is not taken, second will
        # fail with AttributeError.
        declare_bad()
        self.assertRaises(AttributeError, declare_bad)

        # We can specify a new related_name and it will be accepted.
        declare_bad(related_name='valid_backref_name')

        # We can also silence any validation errors.
        declare_bad(backrefs=False)


class TestProxy(PeeweeTestCase):
    def test_proxy(self):
        class A(object):
            def foo(self):
                return 'foo'

        a = Proxy()
        def raise_error():
            a.foo()
        self.assertRaises(AttributeError, raise_error)

        a.initialize(A())
        self.assertEqual(a.foo(), 'foo')

    def test_proxy_database(self):
        database_proxy = Proxy()

        class DummyModel(TestModel):
            test_field = CharField()
            class Meta:
                database = database_proxy

        # Un-initialized will raise an AttributeError.
        self.assertRaises(AttributeError, DummyModel.create_table)

        # Initialize the object.
        database_proxy.initialize(SqliteDatabase(':memory:'))

        # Do some queries, verify it is working.
        DummyModel.create_table()
        DummyModel.create(test_field='foo')
        self.assertEqual(DummyModel.get().test_field, 'foo')
        DummyModel.drop_table()

    def test_proxy_callbacks(self):
        p = Proxy()
        state = {}

        def cb1(obj):
            state['cb1'] = obj
        p.attach_callback(cb1)

        @p.attach_callback
        def cb2(obj):
            state['cb2'] = 'called'

        self.assertEqual(state, {})
        p.initialize('test')
        self.assertEqual(state, {
            'cb1': 'test',
            'cb2': 'called',
        })


@skip_if(lambda: not test_db.window_functions)
class TestWindowFunctions(ModelTestCase):
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
        super(TestWindowFunctions, self).setUp()
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


@skip_if(lambda: not test_db.distinct_on)
class TestDistinctOn(ModelTestCase):
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


@skip_if(lambda: not test_db.for_update)
class TestForUpdate(ModelTestCase):
    requires = [User]

    def tearDown(self):
        test_db.set_autocommit(True)

    def test_for_update(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u3')

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


@skip_if(lambda: not test_db.for_update_nowait)
class TestForUpdateNoWait(ModelTestCase):
    requires = [User]

    def tearDown(self):
        test_db.set_autocommit(True)

    def test_for_update_exc(self):
        u1 = User.create(username='u1')
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
