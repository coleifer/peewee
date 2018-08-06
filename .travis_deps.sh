#!/bin/bash

setup_sqlite_deps() {
  wget https://www.sqlite.org/src/tarball/sqlite.tar.gz
  tar xzf sqlite.tar.gz
  cd sqlite/
  export CFLAGS="-DSQLITE_ENABLE_FTS3 \
    -DSQLITE_ENABLE_FTS3_PARENTHESIS \
    -DSQLITE_ENABLE_FTS4 \
    -DSQLITE_ENABLE_FTS5 \
    -DSQLITE_ENABLE_JSON1 \
    -DSQLITE_ENABLE_LOAD_EXTENSION \
    -DSQLITE_ENABLE_UPDATE_DELETE_LIMIT \
    -DSQLITE_TEMP_STORE=3 \
    -DSQLITE_USE_URI \
    -O2 \
    -fPIC"
  export PREFIX="/usr/local"
  LIBS="-lm" ./configure \
    --disable-tcl \
    --enable-shared \
    --enable-tempstore=always \
    --prefix="$PREFIX"
  make && sudo make install

  cd ext/misc/

  # Build the transitive closure extension and copy shared library.
  gcc -fPIC -O2 -lsqlite3 -shared closure.c -o closure.so
  sudo cp closure.so /usr/local/lib

  # Build the lsm1 extension and copy shared library.
  cd ../lsm1
  export CFLAGS="-fPIC -O2"
  TCCX="gcc -fPIC -O2" make lsm.so
  sudo cp lsm.so /usr/local/lib
}

if [ -n "$PEEWEE_TEST_BUILD_SQLITE" ]; then
  setup_sqlite_deps
fi
