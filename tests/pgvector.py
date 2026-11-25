from peewee import *
from playhouse.pgvector import *

from .base import BaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import requires_models
from .base import skip_unless


db = db_loader('postgres')


def has_pgvector():
    try:
        db.execute_sql('CREATE EXTENSION IF NOT EXISTS vector')
    except Exception:
        return False
    finally:
        db.close()
    return True


PGVECTOR = has_pgvector()


class Item(TestModel):
    embedding = VectorField(3, distance_metric='cosine', index=True)
    half = VectorField(3, 'half')
    bits = VectorField(3, 'bit')
    sparse = VectorField(3, 'sparse')
    genre = TextField(default='')

    class Meta:
        database = db


class Indexed(TestModel):
    half = VectorField(3, 'half', index=True, index_type='ivfflat',
                       index_options={'lists': 5})
    bits = VectorField(3, 'bit', index=True,
                       index_options={'m': 8, 'ef_construction': 32})
    sparse = VectorField(3, 'sparse', 'l1', index=True)

    class Meta:
        database = db


class TestVectorSQL(BaseTestCase):
    def test_create_table(self):
        sql, _ = Item._schema._create_table(False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "item" ("id" SERIAL NOT NULL PRIMARY KEY, '
            '"embedding" VECTOR(3) NOT NULL, "half" HALFVEC(3) NOT NULL, '
            '"bits" BIT(3) NOT NULL, "sparse" SPARSEVEC(3) NOT NULL, '
            '"genre" TEXT NOT NULL)'))

    def test_index(self):
        # The operator class follows the field's metric.
        index, = Item._schema._create_indexes(False)
        self.assertEqual(index.query(), (
            'CREATE INDEX "item_embedding" ON "item" '
            'USING hnsw ("embedding" vector_cosine_ops)', []))

        indexes = Indexed._schema._create_indexes(False)
        self.assertEqual([index.query()[0] for index in indexes], [
            ('CREATE INDEX "indexed_half" ON "indexed" '
             'USING ivfflat ("half" halfvec_l2_ops) WITH (lists=5)'),
            ('CREATE INDEX "indexed_bits" ON "indexed" '
             'USING hnsw ("bits" bit_hamming_ops) '
             'WITH (ef_construction=32, m=8)'),
            ('CREATE INDEX "indexed_sparse" ON "indexed" '
             'USING hnsw ("sparse" sparsevec_l1_ops)')])

    def test_conversion(self):
        f = Item.embedding
        self.assertSQL(f.db_value([1, 0.5, -2]), 'CAST(? AS vector)',
                       ['[1.0,0.5,-2.0]'])
        self.assertEqual(f.python_value('[1,0.5,-2]'), [1., 0.5, -2.])

        # None, SQL expressions and pgvector's text format pass through.
        self.assertTrue(f.db_value(None) is None)
        self.assertTrue(f.db_value(Item.half) is Item.half)
        self.assertSQL(f.db_value('[1,2,3]'), 'CAST(? AS vector)', ['[1,2,3]'])

        self.assertSQL(Item.half.db_value((1, 2, 3)), 'CAST(? AS halfvec)',
                       ['[1.0,2.0,3.0]'])

        # Bits are sent as varbit, so the server checks their length.
        self.assertSQL(Item.bits.db_value([1, 0, True]), 'CAST(? AS varbit)',
                       ['101'])
        self.assertEqual(Item.bits.python_value('101'), [1, 0, 1])

        # Sparse indexes are 0-based in Python and 1-based in the database.
        for value in ({2: 2, 0: 1.5}, [1.5, 0, 2]):
            self.assertSQL(Item.sparse.db_value(value), 'CAST(? AS sparsevec)',
                           ['{1:1.5,3:2.0}/3'])
        self.assertEqual(Item.sparse.python_value('{1:1.5,3:2}/3'),
                         {0: 1.5, 2: 2.})
        self.assertEqual(Item.sparse.python_value('{}/3'), {})

    def test_distance(self):
        self.assertSQL(Item.embedding.distance([1, 0, 0]),
                       '("t1"."embedding" <=> CAST(? AS vector))',
                       ['[1.0,0.0,0.0]'])
        self.assertSQL(Item.half.distance([1, 0, 0]),
                       '("t1"."half" <-> CAST(? AS halfvec))',
                       ['[1.0,0.0,0.0]'])
        self.assertSQL(Item.bits.distance([1, 0, 1]),
                       '("t1"."bits" <~> CAST(? AS varbit))', ['101'])

        for metric, op in (('l2', '<->'), ('ip', '<#>'), ('l1', '<+>')):
            self.assertSQL(Item.embedding.distance(Item.half, metric),
                           '("t1"."embedding" %s "t1"."half")' % op, [])

        # The percent sign is doubled for the database driver.
        self.assertSQL(Item.bits.distance(Item.bits, 'jaccard'),
                       '("t1"."bits" <%%> "t1"."bits")', [])

    def test_equality(self):
        # A list is one vector, not one parameter per element.
        self.assertSQL(Item.embedding == [1, 0, 0],
                       '("t1"."embedding" = CAST(? AS vector))',
                       ['[1.0,0.0,0.0]'])
        self.assertSQL(Item.embedding != Item.half,
                       '("t1"."embedding" != "t1"."half")', [])
        self.assertSQL(Item.embedding == None,
                       '("t1"."embedding" IS NULL)', [])

        # IN takes a list of vectors.
        self.assertSQL(Item.embedding.in_([[1, 0, 0], [0, 1, 0]]),
                       '("t1"."embedding" IN (CAST(? AS vector), '
                       'CAST(? AS vector)))',
                       ['[1.0,0.0,0.0]', '[0.0,1.0,0.0]'])
        self.assertSQL(Item.bits.not_in([[1, 0, 1]]),
                       '("t1"."bits" NOT IN (CAST(? AS varbit)))', ['101'])
        self.assertSQL(Item.embedding << [], '(0 = 1)', [])

    def test_validation(self):
        self.assertRaises(ValueError, VectorField, 3, 'int8')
        self.assertRaises(KeyError, Item.embedding.distance, [1, 0, 0], 'l3')
        self.assertRaises(ValueError, Item.embedding.db_value, [1, 'x', 3])

        # Bytes would be read as one element per byte.
        for value in (b'\x05', bytearray(b'\x05'), memoryview(b'\x05')):
            self.assertRaises(TypeError, Item.bits.db_value, value)
            self.assertRaises(TypeError, Item.embedding.db_value, value)


@skip_unless(PGVECTOR, 'requires pgvector')
class TestVectorModel(ModelTestCase):
    database = db
    requires = [Item]

    def setUp(self):
        super(TestVectorModel, self).setUp()
        for vector, bits in (([1, 1, 1], [0, 0, 0]),
                             ([2, 2, 2], [1, 0, 1]),
                             ([1, 1, 2], [1, 1, 1])):
            Item.create(embedding=vector, half=vector, sparse=vector,
                        bits=bits, genre='g%d' % sum(bits))

    def assertNearest(self, dist, expected, *where):
        query = Item.select(Item.id, dist.alias('d')).order_by(dist, Item.id)
        if where:
            query = query.where(*where)
        self.assertEqual([(i.id, round(i.d, 3)) for i in query], expected)

    def test_distance(self):
        expected = {
            'l2': [(1, 0.), (3, 1.), (2, 1.732)],
            # Inner product is negated, so that nearer is still smaller.
            'ip': [(2, -6.), (3, -4.), (1, -3.)],
            'cosine': [(1, 0.), (2, 0.), (3, 0.057)],
            'l1': [(1, 0.), (3, 1.), (2, 3.)]}
        for field in (Item.embedding, Item.half, Item.sparse):
            for metric, result in expected.items():
                self.assertNearest(field.distance([1, 1, 1], metric), result)

        self.assertNearest(Item.bits.distance([1, 0, 1]),
                           [(2, 0.), (3, 1.), (1, 2.)])
        self.assertNearest(Item.bits.distance([1, 0, 1], 'jaccard'),
                           [(2, 0.), (3, 0.333), (1, 1.)])

    def test_search(self):
        dist = Item.embedding.distance([1, 1, 2])
        query = Item.select().order_by(dist).limit(1)
        self.assertEqual(query.get().embedding, [1., 1., 2.])

        # Filters, including a filter on the distance itself.
        self.assertNearest(dist, [(1, 0.057), (2, 0.057)], Item.genre != 'g3')
        self.assertNearest(dist, [(3, 0.)], dist < 0.01)

    def test_operands(self):
        E = Item.embedding

        # Nearest neighbors of a stored row.
        row = Item.select(E).where(Item.id == 2)
        self.assertNearest(E.distance(row, 'l2'), [(3, 1.414), (1, 1.732)],
                           Item.id != 2)

        self.assertNearest(E.distance(Item.half, 'l2'),
                           [(1, 0.), (2, 0.), (3, 0.)])
        self.assertNearest(E.distance(fn.l2_normalize(E), 'cosine'),
                           [(1, 0.), (2, 0.), (3, 0.)])

    def test_read_write(self):
        item = Item.get(Item.id == 3)
        self.assertEqual((item.embedding, item.half, item.bits, item.sparse), (
            [1., 1., 2.], [1., 1., 2.], [1, 1, 1], {0: 1., 1: 1., 2: 2.}))

        item.embedding = (0, 0.5, 2)
        item.bits = '110'
        item.sparse = {1: 4}
        item.save()
        item = Item.get(Item.id == 3)
        self.assertEqual((item.embedding, item.bits, item.sparse),
                         ([0., 0.5, 2.], [1, 1, 0], {1: 4.}))

        (Item
         .update(embedding=fn.l2_normalize(Item.embedding))
         .where(Item.id == 2)
         .execute())
        item = Item.get(Item.id == 2)
        self.assertEqual([round(v, 3) for v in item.embedding], [.577] * 3)

        # A wrong length is an error, not a padded or truncated vector.
        for field in ('embedding', 'half', 'bits'):
            data = {'embedding': [1, 1, 1], 'half': [1, 1, 1],
                    'bits': [1, 1, 1], 'sparse': {}, field: [1, 1]}
            with self.database.atomic() as txn:
                self.assertRaises(DataError, Item.create, **data)
                txn.rollback()

    def test_equality(self):
        self.assertEqual(Item.get(Item.embedding == [2, 2, 2]).id, 2)
        query = Item.select().where(Item.bits != [1, 0, 1]).order_by(Item.id)
        self.assertEqual([i.id for i in query], [1, 3])

        def ids(expr):
            return [i.id for i in Item.select().where(expr).order_by(Item.id)]

        E = Item.embedding
        self.assertEqual(ids(E.in_([[2, 2, 2], [1, 1, 2]])), [2, 3])
        self.assertEqual(ids(E.not_in([[2, 2, 2], [1, 1, 2]])), [1])
        row = Item.select(E).where(Item.id == 2)
        self.assertEqual(ids(E.in_(row)), [2])
        self.assertEqual(ids(E.not_in(row)), [1, 3])

        data = {'half': [0, 0, 0], 'bits': [0, 0, 0], 'sparse': {}}
        _, created = Item.get_or_create(embedding=[2, 2, 2], defaults=data)
        self.assertFalse(created)
        item, created = Item.get_or_create(embedding=[3, 3, 3], defaults=data)
        self.assertTrue(created)
        self.assertEqual(item.embedding, [3, 3, 3])

    def test_bulk(self):
        items = list(Item.select().order_by(Item.id))
        for i, item in enumerate(items):
            item.embedding = [i, i, 1]
            item.bits = [i % 2, 0, 1]
        Item.bulk_update(items, fields=[Item.embedding, Item.bits])
        self.assertEqual(
            [(i.embedding, i.bits) for i in Item.select().order_by(Item.id)],
            [([0., 0., 1.], [0, 0, 1]),
             ([1., 1., 1.], [1, 0, 1]),
             ([2., 2., 1.], [0, 0, 1])])

        Item.delete().execute()
        Item.insert_many([
            ([1, 2, 3], [1, 2, 3], '000', {}),
            ('[4,5,6]', [4, 5, 6], '111', {})], fields=[
                Item.embedding, Item.half, Item.bits, Item.sparse]).execute()
        Item.bulk_create([Item(embedding=[7, 8, 9], half=[7, 8, 9],
                               bits=[0, 1, 0], sparse={})])
        query = Item.select().order_by(Item.id)
        self.assertEqual([i.embedding for i in query],
                         [[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]])

    def test_aggregates(self):
        # Aggregates are converted on request.
        for field in (Item.embedding, Item.half):
            avg, total = fn.avg(field).coerce(True), fn.sum(field).coerce(True)
            self.assertEqual(Item.select(total).scalar(), [4., 4., 5.])
            self.assertEqual([round(v, 3) for v in Item.select(avg).scalar()],
                             [1.333, 1.333, 1.667])
            empty = Item.select(avg).where(Item.id == 0)
            self.assertTrue(empty.scalar() is None)

    @requires_models(Indexed)
    def test_index(self):
        def indexes(table):
            return sorted(index.sql.split(' USING ')[1]
                          for index in self.database.get_indexes(table)
                          if ' USING btree ' not in index.sql)

        self.assertEqual(indexes('item'),
                         ['hnsw (embedding vector_cosine_ops)'])
        self.assertEqual(indexes('indexed'), [
            "hnsw (bits bit_hamming_ops) WITH (ef_construction='32', m='8')",
            'hnsw (sparse sparsevec_l1_ops)',
            "ivfflat (half halfvec_l2_ops) WITH (lists='5')"])

        Indexed._schema.drop_index(Indexed.bits)
        self.assertEqual(len(indexes('indexed')), 2)
