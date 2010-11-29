import datetime
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import User, Blog, Entry

db_file = os.path.join(os.getcwd(), 'test.db')
engine = create_engine('sqlite:///%s' % db_file)

Session = sessionmaker(bind=engine)
session = Session()

User.metadata.bind = engine

def initialize():
    User.metadata.create_all()

def teardown():
    User.metadata.drop_all()

def create_user(username, active=True):
    u = User(username=username, active=active)
    session.add(u)
    session.commit()
    return u

def create_blog(user, name):
    b = Blog(user=user, name=name)
    session.add(b)
    session.commit()
    return b

def create_entry(blog, title, content, pub_date=None):
    e = Entry(blog=blog, title=title, content=content,
              pub_date=pub_date or datetime.datetime.now())
    session.add(e)
    session.commit()
    return e

def list_users(ordered=False):
    if ordered:
        return list(session.query(User).order_by(User.username))
    else:
        return list(session.query(User))

def list_blogs_for_user(user):
    return list(user.blog_set)

def list_entries_by_user(user):
    return list(session.query(Entry).join(Blog).filter(Blog.user_id==user.id))

def get_user_count():
    return session.query(User).count()

def list_entries_subquery(user):
    pass

def get_user(username):
    return session.query(User).filter_by(username=username).first()

def get_or_create_user(username):
    try:
        user = session.query(User).filter_by(username=username).one()
    except:
        user = User(username=username, active=False)
        session.add(user)
        session.commit()
    return user
