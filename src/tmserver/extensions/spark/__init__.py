import os
import sys
import logging
from flask import current_app

logger = logging.getLogger(__name__)

class Spark(object):

    def __init__(self, app=None):
        """An extension that creates a spark context to submit computational
        tasks to an Apache Spark cluster.

        Parameters
        ----------
        app: flask.Flask, optional
            flask application (default: ``None``)

        Note
        ----
        The preferred way of initializing the extension is via the
        `init_app()` method.

        Examples
        --------
        spark = Spark()
        spark.init_app(app)
        spark.sc.parallelize(['spark', 'test']).count()
        """
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the extension for some flask application. This will create
        a spark context using information provided in the flask configuration.
        The relevant configuration keys are:

        - USE_SPARK, default False
            If `USE_SPARK` is falsy, the sc and sqlc properties will be
            None.
        - SPARK_MASTER, default 'local'
        - SPARK_HOME, deault '/usr/local/Cellar/apache-spark/1.6.0/libexec'
        - SPARK_DB_URL, default 'postgresql://localhost:5432/tissuemaps'
            User information should be provided according to the following
            syntax:
            'postgresql://localhost:5432/tissuemaps?user=USER&password=PW'

        Parameters
        ----------
        app: flask.Flask
            flask application

        Note
        ----
        Requires a JDBC driver for PostgreSQL. Download the driver from
        https://jdbc.postgresql.org/download.html and place it into
        /usr/share/java.
        """

        logger.info('initialize Spark extension')
        use_spark = app.config.get('USE_SPARK')
        app.config.setdefault('SPARK_MASTER', 'local')
        app.config.setdefault(
            'SPARK_DB_URL', 'postgresql://localhost:5432/tissuemaps'
        )
        app.config.setdefault(
            'SPARK_HOME', '/usr/local/Cellar/apache-spark/1.6.0/libexec')

        def create_spark_context(spark_home, spark_master):
            '''Create a Spark Context.

            Parameters
            ----------
            spark_home: str
                path to the directory where Spark was installed on the local
                machine
            spark_master: str
                name of the Spark master node
                (e.g. ``"local"`` or ``"yarn-client"``)

            Returns
            -------
            pyspark.context.SparkContext
                configured Spark Context

            Note
            ----
            Requires the following softlinks:
                * "py4j-src.zip" in $SPARK_HOME/python/lib

            Warning
            -------
            When Spark was not installed and configured via elasticluster,
            the hadoop/yarn configuration must be manually set up.
            '''
            if 'SPARK_HOME' not in os.environ:
                os.environ['SPARK_HOME'] = spark_home
            spark_home = os.environ['SPARK_HOME']
            os.environ.setdefault('MASTER', spark_master)

            spark_home_python = os.path.join(spark_home, 'python')
            sys.path.insert(0, spark_home_python)
            sys.path.insert(0, os.path.join(spark_home_python, 'pyspark'))
            # Requires softlink to the actual file
            sys.path.insert(0, os.path.join(spark_home_python, 'lib', 'py4j-src.zip'))
            spark_pythonpath = '{path}:{path}/pyspark'.format(
                path=spark_home_python
            )
            if 'PYTHONPATH' in os.environ:
                if spark_pythonpath not in os.environ['PYTHONPATH']:
                    os.environ['PYTHONPATH'] += ':' + spark_pythonpath
            else:
                os.environ['PYTHONPATH'] = spark_pythonpath

            from pyspark import SparkConf
            from pyspark import SparkContext
            conf = SparkConf()
            conf.setAppName('tmaps')
            return SparkContext(conf=conf)

        if use_spark:
            logger.info('create Spark context')
            spark_home = app.config.get('SPARK_HOME')
            spark_master = app.config.get('SPARK_MASTER')
            sc = create_spark_context(spark_home, spark_master)
            from pyspark.sql import SQLContext
            sqlc = SQLContext(sc)
            app.extensions['spark'] = {
                'context': sc,
                'sqlcontext': sqlc
            }

    @property
    def sc(self):
        """
        pyspark.SparkContext
            The spark context. If `USE_SPARK` is set to a falsy value this
            property will be None.

        """
        return current_app.extensions.get('spark', {}).get('context')

    @property
    def sqlc(self):
        """
        pyspark.SQLContext
            The spark sql context. If `USE_SPARK` is set to a falsy value
            this property will be None.

        """
        return current_app.extensions.get('spark', {}).get('sqlcontext')

    def df_reader(self, *args, **kwargs):
        from pyspark.sql import DataFrameReader

        db_url = current_app.config.get('SPARK_DB_URL')
        kwargs.setdefault('url', 'jdbc:%s' % db_url)
        return DataFrameReader(self.sqlc).jdbc(*args, **kwargs)

    def read_table(self, table_name):
        """Reads an SQL table for use with Apache Spark.

        Parameters
        ----------
        table_name : str
            Name of the SQL table or aliased SQL query

        Returns
        -------
        pyspark.sql.DataFrame

        Note
        ----
        Caches the :py:class:`pyspark.sql.DataFrame` to speed up computations.

        """
        return self.df_reader(table=table_name).cache()
