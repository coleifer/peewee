from peewee import Cast


class BaseJsonFieldTestCase(object):
    # Subclasses must define these, as well as specifying requires[].
    M = None  # Json model.
    N = None  # "Normal" model.

    def test_json_field(self):
        data = {'k1': ['a1', 'a2'], 'k2': {'k3': 'v3'}}
        j = self.M.create(data=data)
        j_db = self.M.get(j._pk_expr())
        self.assertEqual(j_db.data, data)

    def test_joining_on_json_key(self):
        values = [
            {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
            {'foo': 'bar', 'baze': {'nugget': 'beta'}},
            {'herp': 'derp', 'baze': {'nugget': 'epsilon'}},
            {'herp': 'derp', 'bar': {'nuggie': 'alpha'}},
        ]
        for data in values:
            self.M.create(data=data)

        for value in ['alpha', 'beta', 'gamma', 'delta']:
            self.N.create(data=value)

        query = (self.M
                 .select()
                 .join(self.N, on=(
                     self.N.data == self.M.data['baze']['nugget']))
                 .order_by(self.M.id))
        results = [jm.data for jm in query]
        self.assertEqual(results, [
            {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
            {'foo': 'bar', 'baze': {'nugget': 'beta'}},
        ])

    def test_json_lookup_methods(self):
        data = {
            'gp1': {
                'p1': {'c1': 'foo'},
                'p2': {'c2': 'bar'}},
            'gp2': {}}
        j = self.M.create(data=data)

        def assertLookup(lookup, expected):
            query = (self.M
                     .select(lookup)
                     .where(j._pk_expr())
                     .dicts())
            self.assertEqual(query.get(), expected)

        expr = self.M.data['gp1']['p1']
        assertLookup(expr.alias('p1'), {'p1': '{"c1": "foo"}'})
        assertLookup(expr.as_json().alias('p2'), {'p2': {'c1': 'foo'}})

        expr = self.M.data['gp1']['p1']['c1']
        assertLookup(expr.alias('c1'), {'c1': 'foo'})
        assertLookup(expr.as_json().alias('c2'), {'c2': 'foo'})

        j.data = [
            {'i1': ['foo', 'bar', 'baz']},
            ['nugget', 'mickey']]
        j.save()

        expr = self.M.data[0]['i1']
        assertLookup(expr.alias('i1'), {'i1': '["foo", "bar", "baz"]'})
        assertLookup(expr.as_json().alias('i2'), {'i2': ['foo', 'bar', 'baz']})

        expr = self.M.data[1][1]
        assertLookup(expr.alias('l1'), {'l1': 'mickey'})
        assertLookup(expr.as_json().alias('l2'), {'l2': 'mickey'})

    def test_json_cast(self):
        self.M.create(data={'foo': {'bar': 3}})
        self.M.create(data={'foo': {'bar': 5}})
        query = (self.M
                 .select(Cast(self.M.data['foo']['bar'], 'float') * 1.5)
                 .order_by(self.M.id)
                 .tuples())
        self.assertEqual(query[:], [(4.5,), (7.5,)])

    def test_json_path(self):
        data = {
            'foo': {
                'baz': {
                    'bar': ['i1', 'i2', 'i3'],
                    'baze': ['j1', 'j2'],
                }}}
        j = self.M.create(data=data)

        def assertPath(path, expected):
            query = (self.M
                     .select(path)
                     .where(j._pk_expr())
                     .dicts())
            self.assertEqual(query.get(), expected)

        expr = self.M.data.path('foo', 'baz', 'bar')
        assertPath(expr.alias('p1'), {'p1': '["i1", "i2", "i3"]'})
        assertPath(expr.as_json().alias('p2'), {'p2': ['i1', 'i2', 'i3']})

        expr = self.M.data.path('foo', 'baz', 'baze', 1)
        assertPath(expr.alias('p1'), {'p1': 'j2'})
        assertPath(expr.as_json().alias('p2'), {'p2': 'j2'})

    def test_json_field_sql(self):
        j = (self.M
             .select()
             .where(self.M.data == {'foo': 'bar'}))
        table = self.M._meta.table_name
        self.assertSQL(j, (
            'SELECT "t1"."id", "t1"."data" '
            'FROM "%s" AS "t1" WHERE ("t1"."data" = CAST(? AS %s))')
            % (table, self.M.data._json_datatype))

        j = (self.M
             .select()
             .where(self.M.data['foo'] == 'bar'))
        self.assertSQL(j, (
            'SELECT "t1"."id", "t1"."data" '
            'FROM "%s" AS "t1" WHERE ("t1"."data"->>? = ?)') % table)

    def assertItems(self, where, *items):
        query = (self.M
                 .select()
                 .where(where)
                 .order_by(self.M.id))
        self.assertEqual(
            [item.id for item in query],
            [item.id for item in items])

    def test_lookup(self):
        t1 = self.M.create(data={'k1': 'v1', 'k2': {'k3': 'v3'}})
        t2 = self.M.create(data={'k1': 'x1', 'k2': {'k3': 'x3'}})
        t3 = self.M.create(data={'k1': 'v1', 'j2': {'j3': 'v3'}})
        self.assertItems((self.M.data['k2']['k3'] == 'v3'), t1)
        self.assertItems((self.M.data['k1'] == 'v1'), t1, t3)

        # Valid key, no matching value.
        self.assertItems((self.M.data['k2'] == 'v1'))

        # Non-existent key.
        self.assertItems((self.M.data['not-here'] == 'v1'))

        # Non-existent nested key.
        self.assertItems((self.M.data['not-here']['xxx'] == 'v1'))

        self.assertItems((self.M.data['k2']['xxx'] == 'v1'))

    def test_json_bulk_update_top_level_list(self):
        m1 = self.M.create(data=['a', 'b', 'c'])
        m2 = self.M.create(data=['d', 'e', 'f'])

        m1.data = ['g', 'h', 'i']
        m2.data = ['j', 'k', 'l']
        self.M.bulk_update([m1, m2], fields=[self.M.data])
        m1_db = self.M.get(self.M.id == m1.id)
        m2_db = self.M.get(self.M.id == m2.id)
        self.assertEqual(m1_db.data, ['g', 'h', 'i'])
        self.assertEqual(m2_db.data, ['j', 'k', 'l'])


# Contains additional test-cases suitable for the JSONB data-type.
class BaseBinaryJsonFieldTestCase(BaseJsonFieldTestCase):
    def _create_test_data(self):
        data = [
            {'k1': 'v1', 'k2': 'v2', 'k3': {'k4': ['i1', 'i2'], 'k5': {}}},
            ['a1', 'a2', {'a3': 'a4'}],
            {'a1': 'x1', 'a2': 'x2', 'k4': ['i1', 'i2']},
            list(range(10)),
            list(range(5, 15)),
            ['k4', 'k1']]

        self._bjson_objects = []
        for json_value in data:
            self._bjson_objects.append(self.M.create(data=json_value))

    def assertObjects(self, expr, *indexes):
        query = (self.M
                 .select()
                 .where(expr)
                 .order_by(self.M.id))
        self.assertEqual(
            [bjson.data for bjson in query],
            [self._bjson_objects[index].data for index in indexes])

    def test_contained_by(self):
        self._create_test_data()

        item1 = ['a1', 'a2', {'a3': 'a4'}, 'a5']
        self.assertObjects(self.M.data.contained_by(item1), 1)

        item2 = {'a1': 'x1', 'a2': 'x2', 'k4': ['i0', 'i1', 'i2'], 'x': 'y'}
        self.assertObjects(self.M.data.contained_by(item2), 2)

    def test_equality(self):
        data = {'k1': ['a1', 'a2'], 'k2': {'k3': 'v3'}}
        j = self.M.create(data=data)
        j_db = self.M.get(self.M.data == data)
        self.assertEqual(j.id, j_db.id)

    def test_subscript_contains(self):
        self._create_test_data()
        D = self.M.data

        # 'k3' is mapped to another dictioary {'k4': [...]}. Therefore,
        # 'k3' is said to contain 'k4', but *not* ['k4'] or ['k4', 'k5'].
        self.assertObjects(D['k3'].contains('k4'), 0)
        self.assertObjects(D['k3'].contains(['k4']))
        self.assertObjects(D['k3'].contains(['k4', 'k5']))

        # We can check for the keys this way, though.
        self.assertObjects(D['k3'].contains_all('k4', 'k5'), 0)
        self.assertObjects(D['k3'].contains_any('k4', 'kx'), 0)

        # However, in test object index=2, 'k4' can be said to contain
        # both 'i1' and ['i1'].
        self.assertObjects(D['k4'].contains('i1'), 2)
        self.assertObjects(D['k4'].contains(['i1']), 2)

        # Interestingly, we can also specify the list of contained values
        # out-of-order.
        self.assertObjects(D['k4'].contains(['i2', 'i1']), 2)

        # We can test whether an object contains another JSON object fragment.
        self.assertObjects(D['k3'].contains({'k4': ['i1']}), 0)
        self.assertObjects(D['k3'].contains({'k4': ['i1', 'i2']}), 0)

        # Check multiple levels of nesting / containment.
        self.assertObjects(D['k3']['k4'].contains('i2'), 0)
        self.assertObjects(D['k3']['k4'].contains_all('i1', 'i2'), 0)
        self.assertObjects(D['k3']['k4'].contains_all('i0', 'i2'))
        self.assertObjects(D['k4'].contains_all('i1', 'i2'), 2)

        # Check array indexes.
        self.assertObjects(D[2].contains('a3'), 1)
        self.assertObjects(D[0].contains('a1'), 1)
        self.assertObjects(D[0].contains('k1'))

    def test_contains(self):
        self._create_test_data()
        D = self.M.data

        # Test for keys. 'k4' is both an object key and an array element.
        self.assertObjects(D.contains('k4'), 2, 5)
        self.assertObjects(D.contains('a1'), 1, 2)
        self.assertObjects(D.contains('k3'), 0)

        # We can test for multiple top-level keys/indexes.
        self.assertObjects(D.contains_all('a1', 'a2'), 1, 2)

        # If we test for both with .contains(), though, it is treated as
        # an object match.
        self.assertObjects(D.contains(['a1', 'a2']), 1)

        # Check numbers.
        self.assertObjects(D.contains([2, 5, 6, 7, 8]), 3)
        self.assertObjects(D.contains([5, 6, 7, 8, 9]), 3, 4)

        # We can check for partial objects.
        self.assertObjects(D.contains({'a1': 'x1'}), 2)
        self.assertObjects(D.contains({'k3': {'k4': []}}), 0)
        self.assertObjects(D.contains([{'a3': 'a4'}]), 1)

        # Check for simple keys.
        self.assertObjects(D.contains('a1'), 1, 2)
        self.assertObjects(D.contains('k3'), 0)

        # Contains any.
        self.assertObjects(D.contains_any('a1', 'k1'), 0, 1, 2, 5)
        self.assertObjects(D.contains_any('k4', 'xx', 'yy', '2'), 2, 5)
        self.assertObjects(D.contains_any('i1', 'i2', 'a3'))

        # Contains all.
        self.assertObjects(D.contains_all('k1', 'k2', 'k3'), 0)
        self.assertObjects(D.contains_all('k1', 'k2', 'k3', 'k4'))

        # Has key.
        self.assertObjects(D.has_key('a1'), 1, 2)
        self.assertObjects(D.has_key('k1'), 0, 5)
        self.assertObjects(D.has_key('k4'), 2, 5)
        self.assertObjects(D.has_key('a3'))

        self.assertObjects(D['k3'].has_key('k4'), 0)
        self.assertObjects(D['k4'].has_key('i2'), 2)

    def test_concat_data(self):
        self.M.delete().execute()
        self.M.create(data={'k1': {'x1': 'y1'}, 'k2': 'v2', 'k3': [0, 1]})

        def assertData(exp, expected_data):
            query = self.M.select(self.M.data.concat(exp)).tuples()
            data = query[:][0][0]
            self.assertEqual(data, expected_data)

        D = self.M.data
        assertData({'k2': 'v2-x', 'k1': {'x2': 'y2'}, 'k4': 'v4'}, {
            'k1': {'x2': 'y2'},  # NB: not merged/patched!!
            'k2': 'v2-x',
            'k3': [0, 1],
            'k4': 'v4'})
        assertData({'k1': 'v1-x', 'k3': [2, 3, 4], 'k4': {'x4': 'y4'}}, {
            'k1': 'v1-x',
            'k2': 'v2',
            'k3': [2, 3, 4],
            'k4': {'x4': 'y4'}})

        # We can update sub-keys.
        query = self.M.select(D['k1'].concat({'x2': 'y2', 'x3': 'y3'}))
        self.assertEqual(query.tuples()[0][0],
                         {'x1': 'y1', 'x2': 'y2', 'x3': 'y3'})

        # Concat can be used to extend JSON arrays.
        query = self.M.select(D['k3'].concat([2, 3]))
        self.assertEqual(query.tuples()[0][0], [0, 1, 2, 3])

    def test_update_data_inplace(self):
        self.M.delete().execute()
        b = self.M.create(data={'k1': {'x1': 'y1'}, 'k2': 'v2'})

        self.M.update(data=self.M.data.concat({
            'k1': {'x2': 'y2'},
            'k3': 'v3'})).execute()
        b2 = self.M.get(self.M.id == b.id)
        self.assertEqual(b2.data, {'k1': {'x2': 'y2'}, 'k2': 'v2', 'k3': 'v3'})

    def test_selecting(self):
        self._create_test_data()
        query = (self.M
                 .select(self.M.data['k3']['k4'].as_json().alias('k3k4'))
                 .order_by(self.M.id))
        k3k4_data = [obj.k3k4 for obj in query]
        self.assertEqual(k3k4_data, [
            ['i1', 'i2'],
            None,
            None,
            None,
            None,
            None])

        query = (self.M
                 .select(
                     self.M.data[0].as_json(),
                     self.M.data[2].as_json())
                 .order_by(self.M.id)
                 .tuples())
        self.assertEqual(list(query), [
            (None, None),
            ('a1', {'a3': 'a4'}),
            (None, None),
            (0, 2),
            (5, 7),
            ('k4', None)])

    def test_conflict_update(self):
        b1 = self.M.create(data={'k1': 'v1'})
        iq = (self.M
              .insert(id=b1.id, data={'k1': 'v1-x'})
              .on_conflict('update', conflict_target=[self.M.id],
                           update={self.M.data: {'k1': 'v1-z'}}))
        b1_id_db = iq.execute()
        self.assertEqual(b1.id, b1_id_db)

        b1_db = self.M.get(self.M.id == b1.id)
        self.assertEqual(self.M.data, {'k1': 'v1-z'})

        iq = (self.M
              .insert(id=b1.id, data={'k1': 'v1-y'})
              .on_conflict('update', conflict_target=[self.M.id],
                           update={'data': {'k1': 'v1-w'}}))
        b1_id_db = iq.execute()
        self.assertEqual(b1.id, b1_id_db)

        b1_db = self.M.get(self.M.id == b1.id)
        self.assertEqual(self.M.data, {'k1': 'v1-w'})

        self.assertEqual(self.M.select().count(), 1)
