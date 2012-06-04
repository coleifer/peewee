import datetime

from models import create_tables, drop_tables, User, Blog, Entry


def initialize():
    try:
        create_tables()
    except:
        pass

def teardown():
    drop_tables()

def create_user(username, active=True):
    return User.create(username=username, active=active)

def create_blog(user, name):
    return Blog.create(user=user, name=name)

def create_entry(blog, title, content, pub_date=None):
    return Entry.create(blog=blog, title=title, content=content,
                        pub_date=pub_date or datetime.datetime.now())

def list_users(ordered=False):
    if ordered:
        sq = User.select().order_by('username')
    else:
        sq = User.select()
    return list(sq)

def list_blogs_select_related():
    qs = Blog.select({Blog: ['*'], User: ['*']}).join(User)
    return list(qs)

def list_blogs_for_user(user):
    return list(user.blog_set)

def list_entries_by_user(user):
    return list(Entry.select().join(Blog).where(user=user))

def get_user_count():
    return User.select().count()

def list_entries_subquery(user):
    return list(Entry.select().where(blog__in=Blog.select().where(user=user)))

def get_user(username):
    return User.get(username=username)

def get_or_create_user(username):
    return User.get_or_create(username=username)
