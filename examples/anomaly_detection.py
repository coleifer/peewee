import math
from peewee import *


db = SqliteDatabase(':memory:')

class Reg(Model):
    key = TextField()
    value = IntegerField()

    class Meta:
        database = db


db.create_tables([Reg])

# Create a user-defined aggregate function suitable for computing the standard
# deviation of a series.
@db.aggregate('stddev')
class StdDev(object):
    def __init__(self):
        self.n = 0
        self.values = []

    def step(self, value):
        self.n += 1
        self.values.append(value)

    def finalize(self):
        if self.n < 2:
            return 0
        mean = sum(self.values) / self.n
        sqsum = sum((i - mean) ** 2 for i in self.values)
        return math.sqrt(sqsum / (self.n - 1))


values = [2, 3, 5, 2, 3, 12, 5, 3, 4, 1, 2, 1, -9, 3, 3, 5]

Reg.create_table()
Reg.insert_many([{'key': 'k%02d' % i, 'value': v}
                 for i, v in enumerate(values)]).execute()

# We'll calculate the mean and the standard deviation of the series in a common
# table expression, which will then be used by our query to find rows whose
# zscore exceeds a certain threshold.
cte = (Reg
       .select(fn.avg(Reg.value), fn.stddev(Reg.value))
       .cte('stats', columns=('series_mean', 'series_stddev')))

# The zscore is defined as the (value - mean) / stddev.
zscore = (Reg.value - cte.c.series_mean) / cte.c.series_stddev

# Find rows which fall outside of 2 standard deviations.
threshold = 2
query = (Reg
         .select(Reg.key, Reg.value, zscore.alias('zscore'))
         .from_(Reg, cte)
         .where((zscore >= threshold) | (zscore <= -threshold))
         .with_cte(cte))

for row in query:
    print(row.key, row.value, round(row.zscore, 2))

db.close()
