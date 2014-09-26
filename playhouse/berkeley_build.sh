#!/bin/bash

# This script will download and compile BerkeleyDB with the SQL compat and
# SQLite compatibility layer. Then it grabs a current checkout of pysqlite, the
# standard library SQLite driver, and compiles it against the BerkeleyDB sqlite
# library. You can then choose to install the compiled pysqlite.
#
# By default, the library is downloaded and compiled in a temporary directory,
# ensuring your computer doesn't get cluttered up.
#
# USAGE:
#
# $ virtualenv bdb
# $ cd bdb/
# $ source bin/activate
# (bdb) $ pip install -e git+https://github.com/coleifer/peewee#egg=peewee
# (bdb) $ cd src/peewee/playhouse
# (bdb) $ ./berkeley_build.sh
#
# You can then use the playhouse.berkeley.BerkeleyDatabase class in your
# virtualenv.
#
# To specify a certain BerkeleyDB version, set the environment variable
# BDB_VERSION, e.g.:
# $ BDB_VERSION=6.0.29 ./berkeley_build.sh

# Current version of BerkeleyDB.
BDB_VERSION=${BDB_VERSION:-6.0.30}

# Temporary work dir -- all source will be downloaded and compiled here.
WORK_DIR=${1:-/tmp/bdb-build/}

# BerkeleyDB source code location.
BDB_DOWNLOAD_FILE=${2:-/tmp/bdb.tar.gz}

# When extracted, the directory that contains the BerkeleyDB source.
BDB_SRC_DIR="${WORK_DIR}db-${BDB_VERSION}"

# Destination for the pysqlite source checkout.
PYSQLITE_SRC_DIR="${WORK_DIR}pysqlite"

# Destination for the bsddb3 source checkout.
PYBSDDB3_DIR="${WORK_DIR}bsddb3/"

# Output destination for the compiled BerkeleyDB.
BDB_BUILD_DIR="${WORK_DIR}output/"

get_berkeleydb_source () {
  if [[ ! -f $BDB_DOWNLOAD_FILE ]]; then
    echo "Downloading BerkeleyDB version $BDB_VERSION to $BDB_DOWNLOAD_FILE"
    wget http://download.oracle.com/berkeley-db/db-$BDB_VERSION.tar.gz -O $BDB_DOWNLOAD_FILE
  else
    echo "Found existing BerkeleyDB download in $BDB_DOWNLOAD_FILE"
  fi

  if [[ ! -d $WORK_DIR ]]; then
    echo "BerkeleyDB build directory $WORK_DIR not found."
    mkdir -p $WORK_DIR
  fi

  if [[ ! -d $BDB_SRC_DIR ]]; then
    echo "Source not found in $WORK_DIR, extracting."
    tar xzf $BDB_DOWNLOAD_FILE -C $WORK_DIR
  fi
}

compile_berkeleydb () {
  cd $BDB_SRC_DIR/build_unix
  export CFLAGS="-DSQLITE_ENABLE_FTS3=1 -DSQLITE_ENABLE_RTREE=1 -fPIC"
  ../dist/configure --enable-static --disable-shared --enable-sql --enable-sql-compat
  make clean
  make
  if [[ ! -d $BDB_BUILD_DIR ]]; then
    mkdir $BDB_BUILD_DIR
  fi
  make prefix=$BDB_BUILD_DIR install
}

get_pysqlite_source () {
  git clone https://github.com/ghaering/pysqlite $PYSQLITE_SRC_DIR
  sed -i "s|#\(.*\)=/usr/local/|\1=$BDB_BUILD_DIR|g" $PYSQLITE_SRC_DIR/setup.cfg
}

build_pysqlite () {
  cd $PYSQLITE_SRC_DIR
  python setup.py build
}

install_pysqlite() {
  cd $PYSQLITE_SRC_DIR
  python setup.py install
}

get_bsddb3_source () {
  pip install --download="$WORK_DIR" bsddb3
  TARBALL=`ls ${WORK_DIR}bsddb3* | head -1`
  mkdir $PYBSDDB3_DIR
  tar xzf $TARBALL -C $PYBSDDB3_DIR
}

build_bsddb3 () {
  BSDDB3_SRC_DIR=`ls $PYBSDDB3_DIR | head -1`
  cd "${PYBSDDB3_DIR}/${BSDDB3_SRC_DIR}"
  YES_I_HAVE_THE_RIGHT_TO_USE_THIS_BERKELEY_DB_VERSION=1 python setup.py build --berkeley-db=$BDB_BUILD_DIR
}

install_bsddb3 () {
  BSDDB3_SRC_DIR=`ls $PYBSDDB3_DIR | head -1`
  cd "${PYBSDDB3_DIR}/${BSDDB3_SRC_DIR}"
  YES_I_HAVE_THE_RIGHT_TO_USE_THIS_BERKELEY_DB_VERSION=1 python setup.py install --berkeley-db=$BDB_BUILD_DIR
}

if [[ ! -d $BDB_SRC_DIR ]]; then
  get_berkeleydb_source
else
  echo "BerkeleyDB source found in $BDB_SRC_DIR"
fi

if [[ ! -d $BDB_BUILD_DIR/lib ]]; then
  echo "Compiling BerkeleyDB"
  compile_berkeleydb
else
  echo "BerkeleyDB appears to be compiled in $BDB_BUILD_DIR"
fi

if [[ ! -d $PYSQLITE_SRC_DIR ]]; then
  echo "Fetching source code for pysqlite"
  get_pysqlite_source
else
  echo "Found pysqlite source code in $PYSQLITE_SRC_DIR"
fi

if ! python -c "from pysqlite2 import dbapi2" > /dev/null 2>&1; then
  echo "Pysqlite does not appear to be installed, compiling and building"
  build_pysqlite

  read -p "Install pysqlite now? [Yn] " answer
  if [[ $answer != n ]]; then
    install_pysqlite
  fi
else
  echo "Pysqlite appears to be installed on your system."
fi

if ! python -c "import bsddb3" > /dev/null 2>&1; then
  read -p "OPTIONAL: Install the python BerkeleyDB library bsddb3? [yN] " answer
  if [[ $answer == y ]]; then
    if [[ ! -d $PYBSDDB3_DIR ]]; then
      echo "Downloading bsddb3 python library"
      get_bsddb3_source
    fi
    build_bsddb3
    install_bsddb3
  fi
else
  echo "bsddb3 appears to be installed on your system"
fi
