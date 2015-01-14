#!/usr/bin/env python

from collections import OrderedDict
import datetime
from getpass import getpass
import sys

from peewee import *
from playhouse.sqlcipher_ext import SqlCipherDatabase

# Defer initialization of the database until the script is executed from the
# command-line.
db = SqlCipherDatabase(None)

class Entry(Model):
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db

def initialize(passphrase):
    db.init('diary.db', passphrase=passphrase, kdf_iter=64000)
    Entry.create_table(fail_silently=True)

def menu_loop():
    choice = None
    while choice != 'q':
        for key, value in menu.items():
            print('%s) %s' % (key, value.__doc__))
        choice = raw_input('Action: ').lower().strip()
        if choice in menu:
            menu[choice]()

def add_entry():
    """Add entry"""
    print('Enter your entry. Press ctrl+d when finished.')
    data = sys.stdin.read().strip()
    if data and raw_input('Save entry? [Yn] ') != 'n':
        Entry.create(content=data)
        print('Saved successfully.')

def view_entries(search_query=None):
    """View previous entries"""
    query = Entry.select().order_by(Entry.timestamp.desc())
    if search_query:
        query = query.where(Entry.content.contains(search_query))

    for entry in query:
        timestamp = entry.timestamp.strftime('%A %B %d, %Y %I:%M%p')
        print(timestamp)
        print('=' * len(timestamp))
        print(entry.content)
        print('n) next entry')
        print('d) delete entry')
        print('q) return to main menu')
        action = raw_input('Choice? (Ndq) ').lower().strip()
        if action == 'q':
            break
        elif action == 'd':
            entry.delete_instance()
            break

def search_entries():
    """Search entries"""
    view_entries(raw_input('Search query: '))

menu = OrderedDict([
    ('a', add_entry),
    ('v', view_entries),
    ('s', search_entries),
])

if __name__ == '__main__':
    # Collect the passphrase using a secure method.
    passphrase = getpass('Enter password: ')

    if not passphrase:
        sys.stderr.write('Passphrase required to access diary.\n')
        sys.stderr.flush()
        sys.exit(1)

    # Initialize the database.
    initialize(passphrase)
    menu_loop()
