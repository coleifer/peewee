from peewee import *
from peewee import sqlite3

from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
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
    # CharField (VARCHAR), not TextField: MySQL/MariaDB can't target a TEXT
    # column with a foreign key.
    barcode = CharField(unique=True)


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

    def test_fk_alias_parent(self):
        TA = Tweet.alias('ta')
        with self.assertQueryCount(2):
            query = (TA.select()
                     .order_by(TA.content)
                     .with_related(Load(TA.user,
                                        strategy=PREFETCH_TYPE.MATERIALIZE)))
            accum = [(t.content, t.user.username) for t in query]
        self.assertEqual(accum, [
            ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
            ('purr', 'huey'), ('woof', 'mickey')])

    def test_materialize(self):
        uids = [u.id for u in User.select().order_by(User.id)]

        # MATERIALIZE filters on the parents' in-memory keys (a literal IN-list)
        # rather than a parent subquery. The loaded result is identical.
        with self.assertQueryCount(2) as qh:
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(Load(User.tweets, strategy=PREFETCH_TYPE.MATERIALIZE)))
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
                     .with_related(Load(Tweet.user, strategy=PREFETCH_TYPE.MATERIALIZE)))
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

    def test_forward_fk_relation_filters_parent(self):
        # The relation query excludes some referenced rows; those parents
        # simply are not attached (no error, lazy fallback preserved).
        others = User.select().where(User.username != 'huey')
        for pt in PREFETCH_TYPE.values():
            query = (Tweet
                     .select()
                     .order_by(Tweet.content)
                     .with_related(Load(Tweet.user, others, strategy=pt)))
            got = [(t.content, t.__rel__.get('user')) for t in query]
            self.assertEqual(
                [(c, u.username if u else None) for c, u in got],
                [('bark', 'mickey'), ('hiss', None), ('meow', None),
                 ('purr', None), ('woof', 'mickey')])

    def test_duplicate_parent_rows_hydrated(self):
        # A join-fanned parent query yields the same user twice as distinct
        # instances; each gets its own backref list.
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select(User)
                     .join(Tweet)
                     .where(Tweet.content << ['meow', 'purr'])
                     .with_related(Load(User.tweets, strategy=pt)))
            rows = list(query)
            self.assertEqual([u.username for u in rows], ['huey', 'huey'])
            for u in rows:
                self.assertEqual(sorted(t.content for t in u.tweets),
                                 ['hiss', 'meow', 'purr'])

    def test_limited_parent_subquery(self):
        # MySQL rejects LIMIT directly inside an IN subquery; a limited
        # parent hides behind a derived table (harmless elsewhere).
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .order_by(User.username)
                         .paginate(1, 2)
                         .with_related(Load(User.tweets, strategy=pt)))
                accum = [(u.username, sorted(t.content for t in u.tweets))
                         for u in query]
            self.assertEqual(accum, [
                ('huey', ['hiss', 'meow', 'purr']),
                ('mickey', ['bark', 'woof'])])
            if pt == PREFETCH_TYPE.WHERE:
                sql = self.history[-1].msg[0]
                idx = sql.index('FROM (SELECT')
                self.assertNotIn('LIMIT', sql[:idx])
                self.assertIn('LIMIT', sql[idx:])

    def test_get_with_load_tree(self):
        # get() paginates the parent; the load survives the implicit LIMIT.
        for pt in PREFETCH_TYPE.values():
            user = (User
                    .select()
                    .order_by(User.username)
                    .with_related(Load(User.tweets, strategy=pt))
                    .get())
            self.assertEqual(user.username, 'huey')
            self.assertEqual(sorted(t.content for t in user.tweets),
                             ['hiss', 'meow', 'purr'])

    def test_limited_parent_offset_only(self):
        # OFFSET without LIMIT also hides behind the derived table.
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .order_by(User.username)
                     .offset(1)
                     .with_related(Load(User.tweets, strategy=pt)))
            got = [(u.username, len(u.tweets)) for u in query]
            self.assertEqual(got, [('mickey', 2), ('zaizee', 0)])

    def test_limited_parent_forward_fk(self):
        for pt in PREFETCH_TYPE.values():
            query = (Tweet
                     .select()
                     .order_by(Tweet.content)
                     .limit(2)
                     .with_related(Load(Tweet.user, strategy=pt)))
            got = [(t.content, t.user.username) for t in query]
            self.assertEqual(got, [('bark', 'mickey'), ('hiss', 'huey')])

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
            tweets = (Tweet.select().where(Tweet.published == True)
                      .order_by(Tweet.timestamp.desc()))
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(Load(User.tweets, tweets, strategy=pt)))
                huey, = list(query)

            self.assertEqual([t.content for t in huey.tweets],
                             ['meow', 'purr'])

    def test_query_filters_apply(self):
        # Filters on the relation query restrict the rows loaded for it.
        tweets = (Tweet.select()
                  .where(Tweet.content != 'meow')
                  .where(Tweet.content != 'purr'))
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets)))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['hiss'])

    def test_query_with_joined_source(self):
        # The relation query may join and select from many sources; the joined
        # rows come back attached (DB-side), with no extra query per child.
        for pt in PREFETCH_TYPE.values():
            favorites = (Favorite.select(Favorite, Reaction).join(Reaction)
                         .where(Reaction.name == 'like'))
            with self.assertQueryCount(2):
                query = (Tweet.select().where(Tweet.content == 'meow')
                         .with_related(Load(Tweet.favorites, favorites,
                                            strategy=pt)))
                meow, = list(query)
                reactions = [f.reaction.name for f in meow.favorites]
            self.assertEqual(reactions, ['like'])

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

    def test_explicit_database_propagates(self):
        # The whole load tree runs on the database the parent ran against,
        # so an explicit execute(db) cannot stitch rows from another db.
        alt = get_in_memory_db()
        with alt.bind_ctx([User, Reaction, Tweet, Favorite]):
            alt.create_tables([User, Reaction, Tweet, Favorite])
            u = User.create(username='alt-user')
            r = Reaction.create(name='alt-like')
            t1 = Tweet.create(user=u, content='alt-t1', timestamp=1)
            t2 = Tweet.create(user=u, content='alt-t2', timestamp=2)
            Favorite.create(tweet=t2, reaction=r)

        for pt in PREFETCH_TYPE.values():
            spec = Load(User.tweets, strategy=pt).then(
                Load(Tweet.favorites, strategy=pt))
            rows = list(User.select().with_related(spec).execute(alt))
            got = [(u.username,
                    [(t.content, len(t.favorites))
                     for t in sorted(u.tweets, key=lambda t: t.content)])
                   for u in rows]
            self.assertEqual(got, [
                ('alt-user', [('alt-t1', 0), ('alt-t2', 1)])])

        if not NO_WINDOW_FUNCTIONS:
            newest = Tweet.select().order_by(Tweet.timestamp.desc())
            rows = list(User.select().with_related(
                Load(User.tweets, newest, per_parent=1)).execute(alt))
            got = [(u.username, [t.content for t in u.tweets]) for u in rows]
            self.assertEqual(got, [('alt-user', ['alt-t2'])])

    def test_load_requires_relationship(self):
        self.assertRaises(ValueError, Load, User.username)

    def test_bare_relation_arguments(self):
        # Bare fk/backref references auto-wrap in Load(); junk fails at call
        # time instead of deep inside execution.
        with self.assertQueryCount(2):
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(User.tweets))
            accum = [(u.username, len(u.tweets)) for u in query]
        self.assertEqual(accum, [('huey', 3), ('mickey', 2), ('zaizee', 0)])

        with self.assertQueryCount(3):
            query = (User
                     .select()
                     .where(User.username == 'huey')
                     .with_related(Load(User.tweets).then(Tweet.favorites)))
            huey, = list(query)
            favs = {t.content: len(t.favorites) for t in huey.tweets}
        self.assertEqual(favs, {'meow': 2, 'purr': 0, 'hiss': 0})

        with self.assertQueryCount(2):
            query = (Tweet
                     .select()
                     .order_by(Tweet.content)
                     .with_related(Tweet.user))
            accum = [(t.content, t.user.username) for t in query]
        self.assertEqual(accum, [
            ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
            ('purr', 'huey'), ('woof', 'mickey')])

        self.assertRaises(ValueError,
                          User.select().with_related, User.username)
        self.assertRaises(ValueError, Load(User.tweets).then, Tweet.content)

    def test_load_validates_kwargs(self):
        # Invalid strategy/per_parent values fail at construction instead of
        # silently running WHERE semantics or disabling the limit.
        self.assertRaises(ValueError, Load, User.tweets, strategy='join')
        Load(User.tweets, strategy=PREFETCH_TYPE.JOIN, per_parent=2)
        self.assertRaises(ValueError, prefetch, User.select(), Tweet.select(),
                          prefetch_type='join')

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

    def test_alias_parent_query(self):
        # Parent query selects from an alias: the parent-side key must render
        # against the alias, not the base table.
        for pt in PREFETCH_TYPE.values():
            UA = User.alias('ua')
            with self.assertQueryCount(2):
                query = (UA
                         .select()
                         .order_by(UA.username)
                         .with_related(Load(User.tweets, strategy=pt)))
                backref = [(u.username, sorted(t.content for t in u.tweets))
                           for u in query]
            self.assertEqual(backref, [
                ('huey', ['hiss', 'meow', 'purr']),
                ('mickey', ['bark', 'woof']),
                ('zaizee', [])])

            TA = Tweet.alias('ta')
            with self.assertQueryCount(2):
                query = (TA
                         .select()
                         .order_by(TA.content)
                         .with_related(Load(Tweet.user, strategy=pt)))
                forward = [(t.content, t.user.username) for t in query]
            self.assertEqual(forward, [
                ('bark', 'mickey'), ('hiss', 'huey'), ('meow', 'huey'),
                ('purr', 'huey'), ('woof', 'mickey')])

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

    def test_branching_asymmetric_depth(self):
        # A-(B, C-D): each tweet forks into favorites>reaction (depth 2) and
        # its author (depth 1); the unequal branches populate independently.
        for pt in PREFETCH_TYPE.values():
            spec = Load(User.tweets, strategy=pt).then(
                Load(Tweet.favorites, strategy=pt).then(
                    Load(Favorite.reaction, strategy=pt)),
                Load(Tweet.user, strategy=pt))
            with self.assertQueryCount(5):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(spec))
                huey, = list(query)
                got = {t.content: (sorted(f.reaction.name for f in t.favorites),
                                   t.user.username)
                       for t in huey.tweets}
            self.assertEqual(got, {
                'meow': (['like', 'love'], 'huey'),
                'purr': ([], 'huey'),
                'hiss': ([], 'huey')})

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
        # the parent of a forward-fk relation, whose fk setattr must not
        # leave it falsely dirty (Favorite below is the parent of
        # Load(Favorite.reaction)).
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
        self.assertTrue(query.scalar() >= 1)

    def test_iterator_raises_with_load_tree(self):
        query = User.select().with_related(Load(User.tweets))
        self.assertRaises(ValueError, query.iterator)

    @skip_if(IS_MYSQL)  # first() limits the parent; MySQL can't LIMIT in IN().
    def test_re_execution_preserves_load(self):
        rel = Load(User.tweets,
                   Tweet.select().where(Tweet.content.in_(['hiss', 'purr'])))

        query = (User.select().where(User.username == 'huey')
                 .with_related(rel))
        list(query)  # First execution + load.
        with self.assertQueryCount(2):
            user = query.first()  # Re-execution: parent reload + related load.
        with self.assertQueryCount(0):
            self.assertEqual(sorted(t.content for t in user.tweets),
                             ['hiss', 'purr'])

    def test_objects_eagerly_loads(self):
        # .objects() yields model instances, so the load must fire; only
        # tuple/dict/namedtuple rows are skipped.
        query = (User.select().order_by(User.username)
                 .with_related(Load(User.tweets)).objects())
        with self.assertQueryCount(2):
            accum = [(u.username, sorted(t.content for t in u.tweets))
                     for u in query]
        self.assertEqual(accum, [
            ('huey', ['hiss', 'meow', 'purr']),
            ('mickey', ['bark', 'woof']),
            ('zaizee', [])])

    def test_non_model_constructor_skips_load(self):
        # objects(non-model) rows have no __data__ to bucket on; skip the
        # load like the other non-model row types instead of crashing.
        query = (User.select().order_by(User.username)
                 .with_related(Load(User.tweets)).objects(dict))
        self.assertEqual([row['username'] for row in query],
                         ['huey', 'mickey', 'zaizee'])

    def test_load_rejects_non_model_relation_query(self):
        self.assertRaises(ValueError, Load, User.tweets,
                          Tweet.select().dicts())
        self.assertRaises(ValueError, Load, User.tweets,
                          Tweet.select().tuples())
        self.assertRaises(ValueError, Load, User.tweets,
                          Tweet.select().objects(dict))


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

    def test_self_ref_alias_parent(self):
        # Self-referential alias parent: without alias-aware linking the
        # parent subquery correlates against the child query itself and
        # every backref silently comes back empty.
        FA = Folder.alias()
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (FA
                         .select()
                         .where(FA.parent.is_null())
                         .order_by(FA.name)
                         .with_related(Load(Folder.children, strategy=pt)))
                got = {f.name: sorted(c.name for c in f.children)
                       for f in query}
            self.assertEqual(got, {'a': ['a1', 'a2'], 'b': []})

    def test_forward_fk_null_parent(self):
        # Forward-fk load where some rows have a null fk: the null-parent rows
        # simply get no parent attached, and nothing errors.
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Folder
                         .select()
                         .order_by(Folder.name)
                         .with_related(Load(Folder.parent, strategy=pt)))
                got = {
                    f.name: (f.parent.name if f.parent is not None else None)
                    for f in query}
            self.assertEqual(got, {
                'a': None,
                'a1': 'a',
                'a1x': 'a1',
                'a2': 'a',
                'b': None})


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
        # One LIMIT across the whole relation: N rows total, not per parent;
        # the limit lives on the relation query itself.
        for pt in PREFETCH_TYPE.values():
            tweets = Tweet.select().order_by(Tweet.timestamp).limit(2)
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(Load(User.tweets, tweets, strategy=pt)))
            total = sum(len(user.tweets) for user in query)
            self.assertEqual(total, 2)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit(self):
        for pt in PREFETCH_TYPE.values():
            tweets = Tweet.select().order_by(Tweet.timestamp.desc())
            with self.assertQueryCount(2):
                query = (User
                         .select()
                         .order_by(User.username)
                         .with_related(
                             Load(User.tweets, tweets, strategy=pt,
                                  per_parent=2)))
                got = {u.username: sorted(t.content for t in u.tweets)
                       for u in query}
            self.assertEqual(got, {
                'huey': ['h2', 'h3'],
                'mickey': ['m0', 'm1']})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_materialize(self):
        # Windowed top-N with materialized keys: same result, but the CTE
        # filters on a value-list rather than a parent subquery.
        tweets = Tweet.select().order_by(Tweet.timestamp.desc())
        with self.assertQueryCount(2):
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(
                         Load(User.tweets, tweets, strategy=PREFETCH_TYPE.MATERIALIZE,
                              per_parent=2)))
            got = {u.username: sorted(t.content for t in u.tweets)
                   for u in query}
        self.assertEqual(got, {'huey': ['h2', 'h3'], 'mickey': ['m0', 'm1']})
        self.assertNotIn('IN (SELECT', self.history[-1].msg[0])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_with_children(self):
        # A child relation hangs off a windowed (CTE) relation: the embedded
        # parent query still carries its WITH clause.
        r = Reaction.create(name='like')
        Favorite.create(tweet=self.tweets['h3'], reaction=Reaction.get())
        for pt in PREFETCH_TYPE.values():
            tweets = Tweet.select().order_by(Tweet.timestamp.desc())
            with self.assertQueryCount(3):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(
                             Load(User.tweets, tweets, strategy=pt,
                                  per_parent=2)
                             .then(Load(Tweet.favorites, strategy=pt))))
                huey, = list(query)
                loaded = {t.content: [f.reaction_id for f in t.favorites]
                          for t in huey.tweets}
            self.assertEqual(sorted(loaded), ['h2', 'h3'])
            self.assertEqual(loaded['h3'], [r.id])
            self.assertEqual(loaded['h2'], [])

    def _fan_out_h3(self):
        # Every tweet gets a favorite (join drops nothing); h3 gets two so a
        # one-to-many join multiplies it.
        like = Reaction.create(name='like')
        for content in ['h0', 'h1', 'h2', 'h3']:
            Favorite.create(tweet=self.tweets[content], reaction=like)
        Favorite.create(tweet=self.tweets['h3'], reaction=like)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_one_to_many_join(self):
        # Fanout must collapse to one row per child before ranking: top-2
        # newest is exactly h2, h3, each once (not duplicated h3).
        self._fan_out_h3()
        tweets = Tweet.select().join(Favorite).order_by(Tweet.timestamp.desc())
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .where(User.username == 'huey')
                     .with_related(Load(User.tweets, tweets, strategy=pt,
                                        per_parent=2)))
            huey, = list(query)
            self.assertEqual(sorted(t.content for t in huey.tweets),
                             ['h2', 'h3'])
            self.assertEqual(len(set(id(t) for t in huey.tweets)), 2)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_fanout_materialize(self):
        # The collapse also holds on the materialized (literal IN-list) path.
        self._fan_out_h3()
        tweets = Tweet.select().join(Favorite).order_by(Tweet.timestamp.desc())
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, strategy=PREFETCH_TYPE.MATERIALIZE,
                                    per_parent=2)))
        huey, = list(query)
        self.assertEqual(sorted(t.content for t in huey.tweets), ['h2', 'h3'])
        self.assertNotIn('IN (SELECT', self.history[-1].msg[0])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_fanout_with_children(self):
        # Collapsed windowed parents must still drive a nested child load.
        self._fan_out_h3()
        tweets = Tweet.select().join(Favorite).order_by(Tweet.timestamp.desc())
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(3):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(
                             Load(User.tweets, tweets, strategy=pt,
                                  per_parent=2)
                             .then(Load(Tweet.favorites, strategy=pt))))
                huey, = list(query)
                favs = {t.content: len(t.favorites) for t in huey.tweets}
            self.assertEqual(favs, {'h2': 1, 'h3': 2})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_order_by_fanned_column(self):
        # Ranking BY the fanning column: h3's two favorites hold the highest
        # ids, so without aggregation h3 ranks twice and evicts h2.
        self._fan_out_h3()
        tweets = Tweet.select().join(Favorite).order_by(Favorite.id.desc())
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .where(User.username == 'huey')
                     .with_related(Load(User.tweets, tweets, strategy=pt,
                                        per_parent=2)))
            huey, = list(query)
            self.assertEqual([t.content for t in huey.tweets], ['h3', 'h2'])

        # Ascending ranks by the oldest matching row instead.
        tweets = Tweet.select().join(Favorite).order_by(Favorite.id)
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, per_parent=2)))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['h0', 'h1'])

    def test_per_parent_order_by_sql_literal_rejected(self):
        # A literal cannot be grouped or aggregated into the ranking, so its
        # ordering would be backend-defined; reject it.
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(
                     User.tweets,
                     Tweet.select().order_by(SQL('timestamp DESC')),
                     per_parent=2)))
        self.assertRaises(ValueError, list, query)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_alias_parent(self):
        # Aliased parent + windowed relation: the ranking CTE links against
        # the alias.
        UA = User.alias('ua')
        tweets = Tweet.select().order_by(Tweet.timestamp.desc())
        for pt in PREFETCH_TYPE.values():
            query = (UA
                     .select()
                     .order_by(UA.username)
                     .with_related(Load(User.tweets, tweets, strategy=pt,
                                        per_parent=2)))
            got = {u.username: [t.content for t in u.tweets] for u in query}
            self.assertEqual(got, {
                'huey': ['h3', 'h2'], 'mickey': ['m1', 'm0']})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_order_multi_term(self):
        # Mixed order terms: the fanned column aggregates, the same-table
        # tiebreaker rides along.
        self._fan_out_h3()
        tweets = (Tweet.select().join(Favorite)
                  .order_by(Favorite.id.desc(), Tweet.timestamp))
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, per_parent=2)))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['h3', 'h2'])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_order_by_expression(self):
        # An expression order term aggregates like a plain column.
        tweets = Tweet.select().order_by(Tweet.timestamp * -1)
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, per_parent=2)))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['h3', 'h2'])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_order_nulls_preserved(self):
        # nulls= ordering survives the MIN/MAX aggregation rewrite.
        tweets = Tweet.select().order_by(
            fn.NULLIF(Tweet.content, 'h3').desc(nulls='first'))
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, per_parent=2)))
        huey, = list(query)
        self.assertEqual([t.content for t in huey.tweets], ['h3', 'h2'])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_limit_join_no_fanout(self):
        # A many-to-one join doesn't multiply rows, so the collapse is a no-op.
        tweets = Tweet.select().join(User).order_by(Tweet.timestamp.desc())
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .order_by(User.username)
                     .with_related(Load(User.tweets, tweets, strategy=pt,
                                        per_parent=2)))
            got = {u.username: sorted(t.content for t in u.tweets)
                   for u in query}
            self.assertEqual(got, {
                'huey': ['h2', 'h3'],
                'mickey': ['m0', 'm1']})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_two_level_per_parent(self):
        # per_parent at both relations: top-2 newest tweets per user, then
        # top-1 favorite per tweet.
        like = Reaction.create(name='like')
        love = Reaction.create(name='love')
        Favorite.create(tweet=self.tweets['h3'], reaction=like)
        Favorite.create(tweet=self.tweets['h3'], reaction=love)
        Favorite.create(tweet=self.tweets['h2'], reaction=like)
        for pt in PREFETCH_TYPE.values():
            spec = (Load(User.tweets,
                         Tweet.select().order_by(Tweet.timestamp.desc()),
                         strategy=pt, per_parent=2)
                    .then(Load(Tweet.favorites,
                               Favorite.select().order_by(Favorite.id.desc()),
                               strategy=pt, per_parent=1)))
            with self.assertQueryCount(3):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(spec))
                huey, = list(query)
                got = {t.content: [f.reaction_id for f in t.favorites]
                       for t in huey.tweets}
            self.assertEqual(sorted(got), ['h2', 'h3'])
            self.assertEqual(got['h3'], [love.id])  # top-1 favorite by id desc
            self.assertEqual(got['h2'], [like.id])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_branch_windowed_and_plain_children(self):
        # A windowed child and a plain child hang off the same parent relation.
        like = Reaction.create(name='like')
        for content in ['h0', 'h1', 'h2', 'h3']:
            Favorite.create(tweet=self.tweets[content], reaction=like)
        for pt in PREFETCH_TYPE.values():
            spec = Load(User.tweets, strategy=pt).then(
                Load(Tweet.favorites,
                     Favorite.select().order_by(Favorite.id.desc()),
                     strategy=pt, per_parent=1),
                Load(Tweet.user, strategy=pt))
            with self.assertQueryCount(4):
                query = (User
                         .select()
                         .where(User.username == 'huey')
                         .with_related(spec))
                huey, = list(query)
                got = {t.content: (len(t.favorites), t.user.username)
                       for t in huey.tweets}
            self.assertEqual(got, {
                'h0': (1, 'huey'), 'h1': (1, 'huey'),
                'h2': (1, 'huey'), 'h3': (1, 'huey')})

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_order_by_joined_column(self):
        # Ranking by a (many-to-one) joined column: the window lives in the CTE
        # which has the join; the outer orders by rank, not the joined column.
        a = Reaction.create(name='aaa')
        b = Reaction.create(name='bbb')
        c = Reaction.create(name='ccc')
        t0 = self.tweets['h0']
        for r in (b, a, c):
            Favorite.create(tweet=t0, reaction=r)
        for pt in PREFETCH_TYPE.values():
            favorites = (Favorite.select().join(Reaction)
                         .order_by(Reaction.name.desc()))
            query = (Tweet
                     .select()
                     .where(Tweet.content == 'h0')
                     .with_related(Load(Tweet.favorites, favorites,
                                        strategy=pt, per_parent=2)))
            tweet, = list(query)
            # top-2 by reaction name desc (ccc, bbb), in that order.
            self.assertEqual([f.reaction_id for f in tweet.favorites],
                             [c.id, b.id])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_offset_ignored(self):
        # A relation offset must not leak into the ranking CTE (limit is
        # cleared, so offset must be too) - top-2 newest stays h2, h3.
        tweets = Tweet.select().order_by(Tweet.timestamp.desc()).offset(1)
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, tweets, per_parent=2)))
        huey, = list(query)
        self.assertEqual(sorted(t.content for t in huey.tweets), ['h2', 'h3'])

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_two_level_per_parent_distinct_cte_names(self):
        # Nested windowed relations need distinct CTE names, else the embedded
        # parent CTE collides with the child's on some backends.
        Reaction.create(name='like')
        Favorite.create(tweet=self.tweets['h3'], reaction=Reaction.get())
        spec = (Load(User.tweets,
                     Tweet.select().order_by(Tweet.timestamp.desc()),
                     per_parent=2)
                .then(Load(Tweet.favorites,
                           Favorite.select().order_by(Favorite.id.desc()),
                           per_parent=1)))
        query = (User.select().where(User.username == 'huey')
                 .with_related(spec))
        list(query)
        sql = self.history[-1].msg[0]
        self.assertIn('_load_ranked_0', sql)
        self.assertIn('_load_ranked_1', sql)
        self.assertNotIn('"_load_ranked"', sql)  # bare name would collide

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_custom_projection(self):
        # Same-model computed columns ride the outer re-select: the windowed
        # path returns what the plain path returns.
        rel = (Tweet
               .select(Tweet, fn.LENGTH(Tweet.content).alias('clen'))
               .order_by(Tweet.timestamp.desc()))
        plain = (User
                 .select()
                 .where(User.username == 'huey')
                 .with_related(Load(User.tweets, rel)))
        huey, = list(plain)
        expected = [(t.content, t.clen) for t in huey.tweets][:2]
        for pt in PREFETCH_TYPE.values():
            query = (User
                     .select()
                     .where(User.username == 'huey')
                     .with_related(Load(User.tweets, rel, strategy=pt,
                                        per_parent=2)))
            huey, = list(query)
            self.assertEqual([(t.content, t.clen) for t in huey.tweets],
                             expected)

    @skip_if(NO_WINDOW_FUNCTIONS, 'requires sqlite >= 3.25 for window fns')
    def test_per_parent_projection_to_one_join(self):
        # A to-one join cannot multiply rows, so the outer keeps the join
        # and the selected instances hydrate for free.
        self._fan_out_h3()
        favorites = (Favorite
                     .select(Favorite, Reaction)
                     .join(Reaction)
                     .order_by(Favorite.id.desc()))
        for pt in PREFETCH_TYPE.values():
            with self.assertQueryCount(2):
                query = (Tweet
                         .select()
                         .where(Tweet.content == 'h3')
                         .with_related(Load(Tweet.favorites, favorites,
                                            strategy=pt, per_parent=1)))
                t, = list(query)
                names = [f.reaction.name for f in t.favorites]
            self.assertEqual(names, ['like'])

    def test_per_parent_grouped_relation_rejected(self):
        # per_parent over a grouped/aggregate relation is unsupported (the
        # collapse group-by would include the aggregate); reject it clearly.
        tweets = (Tweet.select().join(Favorite).group_by(Tweet)
                  .order_by(fn.COUNT(Favorite.id).desc()))
        query = User.select().with_related(
            Load(User.tweets, tweets, per_parent=2))
        self.assertRaises(ValueError, list, query)


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
            tags = Tag.select().order_by(Tag.rank.desc())
            with self.assertQueryCount(2):
                query = (Group
                         .select()
                         .with_related(
                             Load(Group.tags, tags, strategy=pt,
                                  per_parent=2)))
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
                     .with_related(Load(Package.items,
                                        strategy=PREFETCH_TYPE.MATERIALIZE)))
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
