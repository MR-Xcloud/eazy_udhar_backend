"""PyMySQL driver for MariaDB on shared VPS (no sudo / no mysqlclient compile)."""

try:
    import pymysql

    pymysql.install_as_MySQLdb()
    # Django 6 requires mysqlclient >= 2.2.1; PyMySQL reports 1.4.x otherwise.
    pymysql.version_info = (2, 2, 1, 'final', 0)
    try:
        import MySQLdb

        MySQLdb.version_info = (2, 2, 1, 'final', 0)
        MySQLdb.__version__ = '2.2.1'
    except ImportError:
        pass
except ImportError:
    pass
