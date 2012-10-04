#!/usr/bin/env python

import os
import sys
import time

sys.path.insert(0, '..')


benchmarks = [dirname for dirname in os.listdir('.') if not os.path.isfile(dirname)]
results = {}

bench_modules = map(__import__, ('%s.bench' % b for b in benchmarks))
bench_modules = map(__import__, ('peewee_bench.bench'))# % b for b in benchmarks))

def run(func, do_cleanup=False, no_time=False):
    if not no_time:
        results[func.__name__] = {}
    for i, m in enumerate(bench_modules):
        try:
            m.bench.initialize()
            start = time.time()
            func(m.bench)
            end = time.time()
            if not no_time:
                results[func.__name__][benchmarks[i]] = end - start
        finally:
            if do_cleanup:
                m.bench.teardown()

def test_creation(m):
    for i in xrange(1000):
        u = m.create_user('user%d' % i)
        b = m.create_blog(u, 'blog%d' % i)
        e = m.create_entry(b, 'entry%d' % i, '')

def test_list_users(m):
    for i in xrange(100):
        users = m.list_users()

def test_list_users_ordered(m):
    for i in xrange(100):
        users = m.list_users(True)

def test_list_blogs_select_related(m):
    for i in xrange(100):
        m.list_blogs_select_related()

def test_get_user_count(m):
    for i in xrange(100):
        m.get_user_count()

def test_get_user(m):
    for i in xrange(100):
        m.get_user('user%d' % i)

    for i in xrange(1000, 1100):
        try:
            m.get_user('user%d' % i)
        except:
            pass

def test_get_or_create_pass(m):
    for i in xrange(100):
        m.get_or_create_user('user%d' % i)

def test_get_or_create_fail(m):
    for i in xrange(1000, 1100):
        m.get_or_create_user('user%d' % i)

def test_prep_lb4u(m):
    for i in xrange(10):
        u = m.create_user('user%d' % i)
        for j in xrange(10):
            m.create_blog(u, 'blog%d' % j)

def test_list_blogs_for_user(m):
    for user in m.list_users():
        for i in xrange(100):
            blogs = m.list_blogs_for_user(user)

def test_prep_le4u(m):
    for i in xrange(10):
        u = m.create_user('user%d' % i)
        b = m.create_blog(u, 'blog%d' % i)
        for j in xrange(10):
            e = m.create_entry(b, 'entry%d' % i, '')

def test_list_entries_for_user(m):
    for user in m.list_users():
        for i in xrange(100):
            entries = m.list_entries_by_user(user)

def test_list_entries_subquery(m):
    for user in m.list_users():
        for i in xrange(100):
            entries = m.list_entries_subquery(user)

def run_all_benches():
    run(test_creation)
    run(test_list_users)
    run(test_list_users_ordered)
    run(test_list_blogs_select_related)
    run(test_get_user)
    run(test_get_or_create_pass)
    run(test_get_or_create_fail)
    run(test_get_user_count, True) # test_list_blogs creates objects
    run(test_prep_lb4u, False, True) # prep "list blogs for user"
    run(test_list_blogs_for_user, True)
    run(test_prep_le4u, False, True)
    run(test_list_entries_for_user)
    run(test_list_entries_subquery, True)


if __name__ == '__main__':
    print 'Running benchmarks for %s' % (', '.join(b for b in benchmarks))
    run_all_benches()

    pw_k = 'peewee_bench'
    non_pw = [b for b in benchmarks if b != pw_k]

    print '%30s |' % (' '),
    for b in benchmarks:
        print '%16s |' % b,
    for b in non_pw:
        print '%s diff |' % (b[:5]),
    print

    for func, result_dict in results.iteritems():
        print '%30s |' % func,
        for b in benchmarks:
            print '%16f |' % result_dict[b],
        pw_res = result_dict[pw_k]
        for b in non_pw:
            print '%9f%% |' % (100 - 100 * (result_dict[pw_k] / result_dict[b])),
        print
