from peewee import *
from peewee import sqlite3

from .base import ModelTestCase
from .base import TestModel
from .base import IS_MYSQL
from .base import IS_SQLITE
from .base import skip_if
from .base import skip_unless


NO_WINDOW_FUNCTIONS = IS_SQLITE and sqlite3.sqlite_version_info < (3, 25)


class User(TestModel):
    username = TextField()


class Tweet(TestModel):
    user = ForeignKeyField(User, backref='tweets')
    content = TextField()
    published = BooleanField(default=True)
    timestamp = IntegerField(default=0)


class Reaction(TestModel):
    name = TextField()


class Favorite(TestModel):
    tweet = ForeignKeyField(Tweet, backref='favorites')
    reaction = ForeignKeyField(Reaction, backref='favorites')


class Message(TestModel):
    sender = ForeignKeyField(User, backref='sent')
    recipient = ForeignKeyField(User, backref='received')
    body = TextField()


class Folder(TestModel):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)


class Group(TestModel):
    name = TextField()


class Tag(TestModel):
    group = ForeignKeyField(Group, backref='tags')
    name = CharField(max_length=255)
    rank = IntegerField(default=0)

    class Meta:
        primary_key = CompositeKey('group', 'name')


class Package(TestModel):
    barcode = TextField(unique=True)


class PackageItem(TestModel):
    name = TextField()
    package = ForeignKeyField(Package, backref='items', field=Package.barcode)


class TestWithRelated(ModelTestCase):
    requires = [User, Reaction, Tweet, Favorite]

    def setUp(self):
        super(TestWithRelated, self).setUp()
        data = (
            ('huey', (
                ('meow', 3, True),
                ('purr', 1, True),
                ('hiss', 2, False))),
            ('mickey', (
                ('woof', 5, True),
                ('bark', 4, True))),
            ('zaizee', ()))
        tweets = {}
        with self.database.atomic():
            for username, rows in data:
                user = User.create(username=username)
                for content, ts, published in rows:
                    tweets[content] = Tweet.create(user=user, content=content,
                                                   timestamp=ts,
                                                   published=published)
            like = Reaction.create(name='like')
            love = Reaction.create(name='love')
            Favorite.create(tweet=tweets['meow'], reaction=like)
            Favorite.create(tweet=tweets['meow'], reaction=love)
            Favorite.create(tweet=tweets['woof'], reaction=like)

    def test_backref(self):
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(Load(User.tweets, strategy=pt)))
                accum = [(u.username, sorted(t.content for t in u.tweets))
                         for u in query]
            self.assertEqual(accum, [
                ('huey', ['hiss', 'meow', 'purr']),
                ('mickey', ['bark', 'woof']),
                ('zaizee', [])])

    def test_materialize(self):
        uids = [u.id for u in User.select().order_by(User.id)]

        # materialize=True embeds the parents' keys as a literal IN-list rather
        # than a parent subquery; the result is identical.
        with self.assertQueryCount(2) as qh:
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(Load(User.tweets, materialize=True)))
            accum = [(u.username, sorted(t.content for t in u.tweets))
                     for u in query]
        self.assertEqual(accum, [
            ('huey', ['hiss', 'meow', 'purr']),
            ('mickey', ['bark', 'woof']),
            ('zaizee', [])])

        sql, params = self.history[-1].msg
        self.assertEqual(sql.count('SELECT'), 1)
        self.assertEqual(sorted(params), uids)

    def test_materialize_forward_fk(self):
        tids = set(t.user_id for t in Tweet.select())

        with self.assertQueryCount(2):
            query = (Tweet
                     .select()
                     .order_by(Tweet.content)
                     .with_related(Load(Tweet.user, materialize=True)))
            accum = [(t.content, t.user.username) for t in query]
        self.assertEqual(accum, [
            ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
            ('purr', 'huey'), ('woof', 'mickey')])

        sql, params = self.history[-1].msg
        self.assertEqual(sql.count('SELECT'), 1)
        self.assertEqual(sorted(params), sorted(tids))

    def test_forward_fk(self):
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Tweet
                         .select()
                         .order_by(Tweet.content)
                         .with_related(Load(Tweet.user, strategy=pt)))
                accum = [(t.content, t.user.username) for t in query]
            self.assertEqual(accum, [
                ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
                ('purr', 'huey'), ('woof', 'mickey')])

    def test_chain(self):
        for pt in PREFETCH_TYPE.values():
            chain = Load(User.tweets, strategy=pt).then(
                Load(Tweet.favorites, strategy=pt).then(
                    Load(Favorite.reaction, strategy=pt)))
            with self.assertQueryCount(4):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(chain))
                accum = []
                for user in query:
                    for tweet in sorted(user.tweets, key=lambda t: t.content):
                        accum.append((
                            user.username, tweet.content,
                            sorted(f.reaction.name for f in tweet.favorites)))
            self.assertEqual(accum, [
                ('huey', 'hiss', []),
                ('huey', 'meow', ['like', 'love']),
                ('huey', 'purr', []),
                ('mickey', 'bark', []),
                ('mickey', 'woof', ['like'])])

    def test_where_and_order_by(self):
        for pt in PREFETCH_TYPE.values():
            spec = (Load(User.tweets, strategy=pt)
                    .where(Tweet.published == True)
                    .order_by(Tweet.timestamp.desc()))
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(spec))
                huey, = list(query)

            self.assertEqual([t.content for t in huey.tweets],
                             ['meow', 'purr'])

    def test_where_accumulates(self):
        # Chained .where() must AND, not overwrite, like every other where().
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(
                     Load(User.tweets)
                     .where(Tweet.content != 'meow')
                     .where(Tweet.content != 'purr')))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['hiss'])

    @skip_if(IS_MYSQL)
    def test_loads_on_every_access_path(self):
        # The load must fire regardless of how rows are materialized - not
        # just iteration. get/first/index/len all go through execute().
        def huey_tweets(user):
            return sorted(t.content for t in user.tweets)

        with self.assertQueryCount(2):
            user = (User.select().where(User.username == 'huey')
                    .with_related(Load(User.tweets)).get())
            self.assertEqual(huey_tweets(user), ['hiss', 'meow', 'purr'])

        with self.assertQueryCount(2):
            user = (User.select().where(User.username == 'huey')
                    .with_related(Load(User.tweets)).first())
            self.assertEqual(huey_tweets(user), ['hiss', 'meow', 'purr'])

        query = (User.select().order_by(User.username)
                 .with_related(Load(User.tweets)))
        self.assertEqual(huey_tweets(query[0]), ['hiss', 'meow', 'purr'])

        query = (User.select().order_by(User.username)
                 .with_related(Load(User.tweets)))
        self.assertEqual(len(query), 3)
        self.assertEqual(huey_tweets(query[0]), ['hiss', 'meow', 'purr'])

    def test_load_requires_relationship(self):
        self.assertRaises(ValueError, Load, User.username)

    def test_load_accepts_model_alias(self):
        # A model alias on the Load reference is accepted and normalized to the
        # base relationship -- the alias has no role in with_related.
        self.assertIs(Load(Tweet.alias().user)._field, Tweet.user)
        self.assertIs(Load(User.alias().tweets)._field, Tweet.user)

        # Forward FK via alias: used to raise "no such column"; now resolves.
        with self.assertQueryCount(2):
            query = (Tweet
                     .select()
                     .order_by(Tweet.content)
                     .with_related(Load(Tweet.alias().user)))
            forward = [(t.content, t.user.username) for t in query]
        self.assertEqual(forward, [
            ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
            ('purr', 'huey'), ('woof', 'mickey')])

        # Backref via alias: was already inert; still loads correctly.
        with self.assertQueryCount(2):
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(Load(User.alias().tweets)))
            backref = [(u.username, sorted(t.content for t in u.tweets))
                       for u in query]
        self.assertEqual(backref, [
            ('huey', ['hiss', 'meow', 'purr']),
            ('mickey', ['bark', 'woof']),
            ('zaizee', [])])

    def test_then_multiple_children(self):
        # A single .then() with two children forks the load: each child row
        # gets both branches populated (here a backref and a forward fk
        # hanging off the same tweet).
        for pt in PREFETCH_TYPE.values():
            spec = Load(User.tweets, strategy=pt).then(
                Load(Tweet.favorites, strategy=pt),
                Load(Tweet.user, strategy=pt))
            with self.assertQueryCount(4):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(spec))
                huey, = list(query)
                fav_counts = {t.content: len(t.favorites) for t in huey.tweets}
                owners = set(t.user.username for t in huey.tweets)
            self.assertEqual(fav_counts, {'meow': 2, 'purr': 0, 'hiss': 0})
            self.assertEqual(owners, {'huey'})

    def test_aggregate_parent(self):
        # An aggregated/grouped parent query loads, and its computed column
        # survives - the load runs against the already-materialized instances.
        for pt in PREFETCH_TYPE.values():
            people = (User
                      .select(User, fn.COUNT(Tweet.id).alias('tweet_count'))
                      .join(Tweet, JOIN.LEFT_OUTER)
                      .group_by(User)
                      .order_by(User.username))
            with self.assertQueryCount(2):
                query = people.with_related(Load(User.tweets, strategy=pt))
                got = {u.username: (u.tweet_count,
                                    sorted(t.content for t in u.tweets))
                       for u in query}
            self.assertEqual(got, {
                'huey': (3, ['hiss', 'meow', 'purr']),
                'mickey': (2, ['bark', 'woof']),
                'zaizee': (0, [])})

    def test_parent_query_with_join(self):
        # The parent query carries its own join and selected parent columns;
        # the JOIN strategy re-embeds it as a subquery, which must still work.
        for pt in PREFETCH_TYPE.values():
            base = (Tweet
                    .select(Tweet, User)
                    .join(User)
                    .order_by(Tweet.content))
            with self.assertQueryCount(2):
                query = base.with_related(Load(Tweet.favorites, strategy=pt))
                got = {t.content: (t.user.username, len(t.favorites))
                       for t in query}
            self.assertEqual(got, {
                'bark': ('mickey', 0), 'hiss': ('huey', 0),
                'meow': ('huey', 2), 'purr': ('huey', 0),
                'woof': ('mickey', 1)})

    def test_no_queries_after_load(self):
        # Once the load has fired, re-iterating the cached query and walking
        # the loaded relations issues no further queries.
        query = (User
                 .select()
                 .order_by(User.username)
                 .with_related(Load(User.tweets).then(Load(Tweet.favorites))))
        list(query)  # Trigger the load.
        with self.assertQueryCount(0):
            accum = [(u.username, t.content, len(t.favorites))
                     for u in query for t in u.tweets]
        self.assertEqual(len(accum), 5)

    def test_loaded_instances_not_dirty(self):
        # Eagerly-loaded instances come back clean, like prefetch() - including
        # the parent of a forward-fk hop, whose fk setattr must not leave it
        # falsely dirty (Favorite below is the parent of Load(Favorite.reaction)).
        query = User.select().with_related(
            Load(User.tweets).then(
                Load(Tweet.favorites).then(
                    Load(Favorite.reaction))))
        for user in query:
            self.assertEqual(user.dirty_fields, [])
            for tweet in user.tweets:
                self.assertEqual(tweet.dirty_fields, [])
                for fav in tweet.favorites:
                    self.assertEqual(fav.dirty_fields, [])
                    self.assertEqual(fav.reaction.dirty_fields, [])

    def test_exists_and_scalar_ignore_load_tree(self):
        query = User.select().with_related(Load(User.tweets))
        self.assertTrue(query.exists())
        self.assertEqual(query.scalar(), 1)

    def test_iterator_raises_with_load_tree(self):
        query = User.select().with_related(Load(User.tweets))
        self.assertRaises(ValueError, query.iterator)

    def test_re_execution_preserves_load(self):
        # After the query has been executed once, get()/first() must still
        # eagerly load related rows on the fresh instances they return.
        query = (User.select().where(User.username == 'huey')
                 .with_related(Load(User.tweets)))
        list(query)
        with self.assertQueryCount(2):
            user = query.first()
            self.assertEqual(sorted(t.content for t in user.tweets),
                             ['hiss', 'meow', 'purr'])


class TestWithRelatedMultiFK(ModelTestCase):
    requires = [User, Message]

    def setUp(self):
        super(TestWithRelatedMultiFK, self).setUp()
        huey = User.create(username='huey')
        mickey = User.create(username='mickey')
        Message.create(sender=huey, recipient=mickey, body='to mickey')
        Message.create(sender=mickey, recipient=huey, body='to huey')

    def test_only_named_relationship_loaded(self):
        # Two FKs to User; loading one backref must not populate the sibling
        # or cross-contaminate it.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(Load(User.received, strategy=pt)))
                users = {u.username: u for u in query}
            self.assertEqual([m.body for m in users['huey'].received],
                             ['to huey'])
            self.assertEqual([m.body for m in users['mickey'].received],
                             ['to mickey'])
            self.assertIn('received', users['huey'].__dict__)
            self.assertNotIn('sent', users['huey'].__dict__)

    def test_multiple_top_level_loads(self):
        # Two independent Load nodes in one with_related() call: both backrefs
        # to User are populated, neither leaks into the other.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(3):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(Load(User.sent, strategy=pt),
                                       Load(User.received, strategy=pt)))
                users = {u.username: u for u in query}
            self.assertEqual([m.body for m in users['huey'].sent],
                             ['to mickey'])
            self.assertEqual([m.body for m in users['huey'].received],
                             ['to huey'])
            self.assertEqual([m.body for m in users['mickey'].sent],
                             ['to huey'])
            self.assertEqual([m.body for m in users['mickey'].received],
                             ['to mickey'])


class TestWithRelatedSelfRef(ModelTestCase):
    requires = [Folder]

    def setUp(self):
        super(TestWithRelatedSelfRef, self).setUp()
        a = Folder.create(name='a')
        b = Folder.create(name='b')
        a1 = Folder.create(name='a1', parent=a)
        Folder.create(name='a2', parent=a)
        Folder.create(name='a1x', parent=a1)

    def test_self_ref_two_levels(self):
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(3):
                query = (Folder
                         .select()
                         .where(Folder.parent.is_null())
                         .order_by(Folder.name)
                         .with_related(
                             Load(Folder.children, strategy=pt).then(
                                 Load(Folder.children, strategy=pt))))
                tree = {}
                for root in query:
                    tree[root.name] = {
                        child.name: sorted(g.name for g in child.children)
                        for child in root.children}
            self.assertEqual(tree, {
                'a': {'a1': ['a1x'], 'a2': []},
                'b': {}})

    def test_forward_fk_null_parent(self):
        # Forward-fk load where some rows have a null fk: the null-parent rows
        # simply get no parent attached, and nothing errors.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Folder
                         .select()
                         .order_by(Folder.name)
                         .with_related(Load(Folder.parent, strategy=pt)))
                got = {f.name: (f.parent.name if f.parent is not None else None)
                       for f in query}
            self.assertEqual(got, {
                'a': None, 'a1': 'a', 'a1x': 'a1', 'a2': 'a', 'b': None})


class TestWithRelatedLimit(ModelTestCase):
    requires = [User, Reaction, Tweet, Favorite]

    def setUp(self):
        super(TestWithRelatedLimit, self).setUp()
        huey = User.create(username='huey')
        mickey = User.create(username='mickey')
        self.tweets = {}
        for i, content in enumerate(['h0', 'h1', 'h2', 'h3']):
            self.tweets[content] = Tweet.create(user=huey, content=content,
                                                timestamp=i)
        for i, content in enumerate(['m0', 'm1']):
            self.tweets[content] = Tweet.create(user=mickey, content=content,
                                                timestamp=i)

    def test_global_limit(self):
        # One LIMIT across the whole hop: N rows total, not per parent.
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(
                         Load(User.tweets, strategy=pt)
                         .order_by(Tweet.timestamp)
                         .limit(2)))
            total = sum(len(user.tweets) for user in query)
            self.assertEqual(total, 2)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit(self):
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(
                             Load(User.tweets, strategy=pt)
                             .order_by(Tweet.timestamp.desc())
                             .limit(2, per_parent=True)))
                got = {u.username: sorted(t.content for t in u.tweets)
                       for u in query}
            self.assertEqual(got, {
                'huey': ['h2', 'h3'],
                'mickey': ['m0', 'm1']})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_materialize(self):
        # Windowed top-N with materialized keys: same result, but the CTE
        # filters on a value-list rather than a parent subquery.
        with self.assertQueryCount(2):
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(
                         Load(User.tweets, materialize=True)
                         .order_by(Tweet.timestamp.desc())
                         .limit(2, per_parent=True)))
            got = {u.username: sorted(t.content for t in u.tweets)
                   for u in query}
        self.assertEqual(got, {'huey': ['h2', 'h3'], 'mickey': ['m0', 'm1']})
        self.assertNotIn('IN (SELECT', self.history[-1].msg[0])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_with_children(self):
        # A child hop hangs off a windowed (CTE) hop: the parent query embedded
        # for the grandchildren still carries its WITH clause.
        Reaction.create(name='like')
        Favorite.create(tweet=self.tweets['h3'], reaction=Reaction.get())
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(3):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(
                             Load(User.tweets, strategy=pt)
                             .order_by(Tweet.timestamp.desc())
                             .limit(2, per_parent=True)
                             .then(Load(Tweet.favorites, strategy=pt))))
                huey, = list(query)
                loaded = {t.content: [f.reaction_id for f in t.favorites]
                          for t in huey.tweets}
            self.assertEqual(sorted(loaded), ['h2', 'h3'])
            self.assertEqual(loaded['h3'], [1])
            self.assertEqual(loaded['h2'], [])


@skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
class TestWithRelatedCompositeKey(ModelTestCase):
    requires = [Group, Tag]

    def setUp(self):
        super(TestWithRelatedCompositeKey, self).setUp()
        group = Group.create(name='g')
        for i, name in enumerate(['t0', 't1', 't2']):
            Tag.create(group=group, name=name, rank=i)

    def test_per_parent_limit_composite_pk(self):
        # The windowed join-back must handle a composite primary key.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Group
                         .select()
                         .with_related(
                             Load(Group.tags, strategy=pt)
                             .order_by(Tag.rank.desc())
                             .limit(2, per_parent=True)))
                group, = list(query)
                names = sorted(t.name for t in group.tags)
            self.assertEqual(names, ['t1', 't2'])


class TestWithRelatedNonPKFK(ModelTestCase):
    requires = [Package, PackageItem]

    def setUp(self):
        super(TestWithRelatedNonPKFK, self).setUp()
        data = (('101', ('a', 'b')),
                ('102', ()),
                ('104', ('a', 'b', 'c')))
        for barcode, items in data:
            Package.create(barcode=barcode)
            for name in items:
                PackageItem.create(package=barcode, name=name)

    def test_backref_non_pk_fk(self):
        # The fk targets Package.barcode, not the pk; bucketing keys on
        # rel_field, so this exercises a different path than a pk-based fk.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Package
                         .select()
                         .order_by(Package.barcode)
                         .with_related(Load(Package.items, strategy=pt)))
                got = {p.barcode: sorted(i.name for i in p.items)
                       for p in query}
            self.assertEqual(got, {
                '101': ['a', 'b'], '102': [], '104': ['a', 'b', 'c']})

    def test_backref_non_pk_fk_materialize(self):
        with self.assertQueryCount(2):
            query = (Package
                     .select()
                     .order_by(Package.barcode)
                     .with_related(Load(Package.items, materialize=True)))
            got = {p.barcode: sorted(i.name for i in p.items) for p in query}
        self.assertEqual(got, {
            '101': ['a', 'b'], '102': [], '104': ['a', 'b', 'c']})
        # The IN-list is built from barcodes (the rel_field), not pks.
        sql, params = self.history[-1].msg
        self.assertEqual(sql.count('SELECT'), 1)
        self.assertEqual(sorted(params), ['101', '102', '104'])

    def test_forward_non_pk_fk(self):
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (PackageItem
                         .select()
                         .order_by(PackageItem.name, PackageItem.id)
                         .with_related(Load(PackageItem.package, strategy=pt)))
                got = sorted((i.name, i.package.barcode) for i in query)
            self.assertEqual(got, [
                ('a', '101'), ('a', '104'),
                ('b', '101'), ('b', '104'),
                ('c', '104')])
