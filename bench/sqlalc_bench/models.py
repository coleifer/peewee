import os

from sqlalchemy import (Table, Column, Integer, String, Boolean, DateTime,
                        ForeignKey)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref


Base = declarative_base()

class User(Base):
    __tablename__ = 'sqlalc_users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String)
    active = Column(Boolean)


class Blog(Base):
    __tablename__ = 'sqlalc_blogs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('sqlalc_users.id'))
    name = Column(String)

    user = relationship(User, backref=backref('blog_set'))


class Entry(Base):
    __tablename__ = 'sqlalc_entries'

    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey('sqlalc_blogs.id'))
    title = Column(String)
    content = Column(String)
    pub_date = Column(DateTime)

    blog = relationship(Blog, backref=backref('entry_set'))
