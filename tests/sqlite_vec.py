from peewee import *
from peewee import sqlite3
from playhouse.sqlite_vec import *

from .base import BaseTestCase
from .base import ModelTestCase
from .base import requires_models
from .base import skip_unless


def vec_extension():
    try:
        import sqlite_vec
    except ImportError:
        path = './vec0'
    else:
        path = sqlite_vec.loadable_path()

    conn = sqlite3.connect(':memory:')
    try:
        conn.enable_load_extension(True)
        conn.load_extension(path)
    except Exception:
        return None
    finally:
        conn.close()
    return path


VEC_EXTENSION = vec_extension()
database = SqliteDatabase(':memory:')
if VEC_EXTENSION:
    database.load_extension(VEC_EXTENSION)


class User(Model):
    name = TextField()

    class Meta:
        database = database


class Chunk(VecModel):
    embedding = VectorField(4, distance_metric='cosine')
    user = ForeignKeyField(User, index=False,
                           constraints=[SQL('PARTITION KEY')])
    genre = TextField()
    score = FloatField()
    body = TextField(unindexed=True)

    class Meta:
        database = database
        options = {'chunk_size': 8}


class Doc(VecModel):
    id = TextField(primary_key=True)
    e8 = VectorField(4, 'int8')
    bits = VectorField(8, 'bit')

    class Meta:
        database = database


class Flag(VecModel):
    embedding = VectorField(2)
    active = BooleanField()
    seen = BooleanField(unindexed=True)

    class Meta:
        database = database


class Item(Model):
    name = TextField()
    embedding = VectorField(3)

    class Meta:
        database = database


class Packed(Model):
    a = VectorField(4, 'int8')
    b = VectorField(4, 'int8')
    bits = VectorField(8, 'bit')

    class Meta:
        database = database


class TestVecSQL(BaseTestCase):
    database = database

    def test_create_table(self):
        self.assertSQL(Chunk._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "chunk" USING vec0 ('
            'embedding float[4] distance_metric=cosine, '
            'user_id integer PARTITION KEY, genre text, score float, '
            '+body text, chunk_size=8)'), [])

        self.assertSQL(Doc._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "doc" USING vec0 ('
            'id text PRIMARY KEY, e8 int8[4], bits bit[8])'), [])

        # Booleans are integers, as metadata and as auxiliary columns.
        self.assertSQL(Flag._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "flag" USING vec0 ('
            'embedding float[2], active integer, +seen integer)'), [])

        # Regular tables store vectors as plain blobs.
        self.assertSQL(Item._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "item" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, "name" TEXT NOT NULL, '
            '"embedding" BLOB NOT NULL)'), [])

    def test_conversion(self):
        f = Chunk.embedding
        blob = f.db_value([1, 0.5])
        self.assertEqual(f.python_value(blob), [1.0, 0.5])
        for value in (None, b'\x00', '[1,0]'):
            self.assertEqual(f.db_value(value), value)

        # The first bit is the least-significant.
        self.assertSQL(Doc.bits.match([1, 0, 0, 0, 0, 0, 0, 1]),
                       '("t1"."bits" MATCH vec_bit(?))', [b'\x81'])
        self.assertEqual(Doc.bits.python_value(b'\x81'),
                         [1, 0, 0, 0, 0, 0, 0, 1])

        self.assertSQL(Doc.e8.match([1, -1, 2, -2]),
                       '("t1"."e8" MATCH vec_int8(?))', [b'\x01\xff\x02\xfe'])
        self.assertEqual(Doc.e8.python_value(b'\x01\xff'), [1, -1])

    def test_search(self):
        query = Chunk.search([1, 0, 0, 0], 3).where(Chunk.genre == 'a')
        self.assertSQL(query, (
            'SELECT "t1"."rowid", "t1"."distance", "t1"."k", '
            '"t1"."embedding", "t1"."user_id", "t1"."genre", "t1"."score", '
            '"t1"."body" FROM "chunk" AS "t1" '
            'WHERE ((("t1"."embedding" MATCH ?) AND ("t1"."k" = ?)) AND '
            '("t1"."genre" = ?)) ORDER BY "t1"."distance"'),
            [Chunk.embedding.db_value([1, 0, 0, 0]), 3, 'a'])
        self.assertRaises(ValueError, Doc.search, [1, 2, 3, 4], 1)

    def test_distance(self):
        self.assertSQL(Chunk.embedding.distance(Chunk.embedding),
                       'vec_distance_cosine("t1"."embedding", '
                       '"t1"."embedding")', [])
        self.assertSQL(Doc.bits.distance(Doc.bits),
                       'vec_distance_hamming(vec_bit("t1"."bits"), '
                       'vec_bit("t1"."bits"))', [])
        self.assertSQL(Packed.a.distance([1, 2, 3, 4]),
                       'vec_distance_l2(vec_int8("t1"."a"), vec_int8(?))',
                       [b'\x01\x02\x03\x04'])
        self.assertSQL(Item.embedding.distance([1, 0, 0], 'L1'),
                       'vec_distance_l1("t1"."embedding", ?)',
                       [Item.embedding.db_value([1, 0, 0])])

    def test_validation(self):
        def assertInvalid(exc, **attrs):
            attrs.setdefault('embedding', VectorField(4))
            self.assertRaises(exc, type, 'Bad', (VecModel,), attrs)

        assertInvalid(ImproperlyConfigured, created=DateTimeField())
        assertInvalid(ImproperlyConfigured, a=TextField(column_name='a b'))
        assertInvalid(ImproperlyConfigured, a=TextField(index=True))
        assertInvalid(ImproperlyConfigured, user=ForeignKeyField(User))
        self.assertRaises(ValueError, VectorField, 12, 'bit')
        self.assertRaises(ValueError, VectorField, 4, 'float16')


@skip_unless(VEC_EXTENSION, 'requires sqlite-vec')
class TestVecModel(ModelTestCase):
    database = database
    requires = [User, Chunk]

    def setUp(self):
        super(TestVecModel, self).setUp()
        self.u1 = User.create(name='u1')
        self.u2 = User.create(name='u2')
        Chunk.insert_many([
            ([1, 0, 0, 0], self.u1, 'a', 1., 'c1'),
            ([0, 1, 0, 0], self.u1, 'b', 2., 'c2'),
            ('[0.5, 0.5, 0, 0]', self.u2, 'a', 3., 'c3'),
        ], fields=[Chunk.embedding, Chunk.user, Chunk.genre, Chunk.score,
                   Chunk.body]).execute()

    def assertSearch(self, query, expected):
        self.assertEqual([(c.body, round(c.distance, 3)) for c in query],
                         expected)

    def test_search(self):
        q = [1, 0, 0, 0]
        self.assertSearch(Chunk.search(q, 3), [
            ('c1', 0.), ('c3', 0.293), ('c2', 1.)])
        self.assertSearch(Chunk.search(q, 1), [('c1', 0.)])

        # Metadata and partition key filters apply before k.
        self.assertSearch(Chunk.search(q, 1).where(Chunk.genre == 'b'),
                          [('c2', 1.)])
        self.assertSearch(Chunk.search(q, 3).where(Chunk.user == self.u2),
                          [('c3', 0.293)])
        self.assertSearch(Chunk.search(q, 3).where(Chunk.score > 1.5),
                          [('c3', 0.293), ('c2', 1.)])

        # LIMIT may replace k.
        query = (Chunk
                 .select(Chunk.body, Chunk.distance)
                 .where(Chunk.embedding.match(q))
                 .order_by(Chunk.distance)
                 .limit(2))
        self.assertSearch(query, [('c1', 0.), ('c3', 0.293)])

    def test_search_join(self):
        query = (Chunk
                 .search([0, 1, 0, 0], 2)
                 .select(Chunk.body, User.name)
                 .join(User))
        self.assertEqual([(c.body, c.user.name) for c in query],
                         [('c2', 'u1'), ('c3', 'u2')])

    def test_read_write(self):
        c = Chunk.create(embedding=[0, 0, 1, 0], user=self.u2, genre='c',
                         score=4., body='c4')
        c_db = Chunk.get(Chunk.rowid == c.rowid)
        self.assertEqual(c_db.embedding, [0., 0., 1., 0.])
        self.assertEqual((c_db.user_id, c_db.genre), (self.u2.id, 'c'))

        # Only the changed column is written, as vec0 cannot update the
        # partition key.
        c_db.genre = 'd'
        c_db.embedding = [0, 0, 0, 1]
        c_db.save()
        c_db = Chunk.get(Chunk.rowid == c.rowid)
        self.assertEqual((c_db.genre, c_db.embedding), ('d', [0, 0, 0, 1.]))

        c_db.delete_instance()
        self.assertEqual(Chunk.select().count(), 3)

    @requires_models(Doc)
    def test_int8_bit(self):
        Doc.create(id='a', e8=[1, 2, 3, 4], bits=[1, 1, 1, 1, 0, 0, 0, 0])
        Doc.create(id='b', e8=[-1, 2, 3, 4],
                   bits=fn.vec_quantize_binary('[1,1,-1,-1,-1,-1,-1,-1]'))

        self.assertEqual([(d.id, d.e8, d.bits) for d in Doc.select()], [
            ('a', [1, 2, 3, 4], [1, 1, 1, 1, 0, 0, 0, 0]),
            ('b', [-1, 2, 3, 4], [1, 1, 0, 0, 0, 0, 0, 0])])

        query = Doc.search([1, 2, 3, 4], 2, Doc.e8)
        self.assertEqual([(d.id, d.distance) for d in query],
                         [('a', 0.), ('b', 2.)])
        query = Doc.search([1, 1, 0, 0, 0, 0, 0, 0], 2, Doc.bits)
        self.assertEqual([(d.id, d.distance) for d in query],
                         [('b', 0.), ('a', 2.)])

        dist = Doc.e8.distance([1, 2, 3, 4])
        query = Doc.select(Doc.id, dist.alias('d')).order_by(dist)
        self.assertEqual([(d.id, d.d) for d in query], [('a', 0.), ('b', 2.)])

    @requires_models(Flag)
    def test_boolean(self):
        Flag.create(embedding=[1, 0], active=True, seen=False)
        Flag.create(embedding=[0, 1], active=False, seen=True)
        self.assertEqual([(f.active, f.seen) for f in Flag.select()],
                         [(True, False), (False, True)])

        query = Flag.search([1, 0], 2).where(Flag.active == False)
        self.assertEqual([(f.active, f.seen) for f in query],
                         [(False, True)])

    @requires_models(Item)
    def test_regular_table(self):
        Item.create(name='x', embedding=[1, 0, 0])
        Item.create(name='y', embedding=[0, 1, 0])
        self.assertEqual(Item.get(Item.name == 'y').embedding, [0., 1., 0.])

        dist = Item.embedding.distance([0, 1, 0.1])
        query = Item.select(Item.name).order_by(dist).limit(1)
        self.assertEqual(query.get().name, 'y')

        dist = Item.embedding.distance([2, 0, 0], 'cosine')
        query = Item.select(Item.name, dist.alias('d')).order_by(dist)
        self.assertEqual([(i.name, i.d) for i in query],
                         [('x', 0.), ('y', 1.)])

    @requires_models(Packed)
    def test_regular_table_int8_bit(self):
        Packed.create(a=[1, 2, 3, 4], b=[1, 2, 3, 6],
                      bits=[1, 1, 0, 0, 0, 0, 0, 0])

        # A stored blob has no element type, so distance() tags the column.
        query = Packed.select(
            Packed.a.distance([1, 2, 3, 5]),
            Packed.a.distance(Packed.b),
            Packed.a.distance(Packed.b, 'l1'),
            Packed.bits.distance([1, 0, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(query.tuples().get(), (1., 2., 2., 1.))
