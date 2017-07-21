#!/usr/bin/env python

import sys
sys.path.insert(0, '../..')

from app import app, database, User, Relationship, Message
with database:
    database.create_tables([User, Relationship, Message])
app.run()
