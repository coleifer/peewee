#
# Small example demonstrating the use of zlib compression with the Sqlite
# full-text search extension.
#
import zlib

from peewee import *
from playhouse.sqlite_ext import *


db = SqliteExtDatabase(':memory:')

class SearchIndex(FTSModel):
    content = SearchField()

    class Meta:
        database = db


@db.func('zlib_compress')
def _zlib_compress(data):
    if data is not None:
        if isinstance(data, str):
            data = data.encode('utf8')
        return zlib.compress(data, 9)

@db.func('zlib_decompress')
def _zlib_decompress(data):
    if data is not None:
        return zlib.decompress(data)


SearchIndex.create_table(
    tokenize='porter',
    compress='zlib_compress',
    uncompress='zlib_decompress')

phrases = [
    'A faith is a necessity to a man. Woe to him who believes in nothing.',
    ('All who call on God in true faith, earnestly from the heart, will '
     'certainly be heard, and will receive what they have asked and desired.'),
    ('Be faithful in small things because it is in them that your strength '
     'lies.'),
    ('Faith consists in believing when it is beyond the power of reason to '
     'believe.'),
    ('Faith has to do with things that are not seen and hope with things that '
     'are not at hand.')]

for phrase in phrases:
    SearchIndex.create(content=phrase)

# Use the simple ranking algorithm.
query = SearchIndex.search('faith things', with_score=True)
for row in query:
    print(round(row.score, 2), row.content.decode('utf8'))

print('---')

# Use the Okapi-BM25 ranking algorithm.
query = SearchIndex.search_bm25('believe', with_score=True)
for row in query:
    print(round(row.score, 2), row.content.decode('utf8'))

db.close()
