import sys
import os
from os.path import join, dirname, abspath
import logging
from flask import Flask
from flask_sqlalchemy_session import flask_scoped_session
import gc3libs

from tmlib.models.utils import (
    create_db_engine, create_db_session_factory, set_db_uri
)

from tmserver.extensions import jwt
from tmserver.extensions import redis_store
from tmserver.serialize import TmJSONEncoder
from tmserver import cfg


logger = logging.getLogger(__name__)


def create_app(config_overrides={}, log_level=None):
    """Create a Flask application object that registers all the blueprints on
    which the actual routes are defined.

    The default settings for this app are contained in 'config/default.py'.
    Additional can be supplied to this method as a dict-like config argument.

    """
    app = Flask('wsgi')

    if log_level is not None:
        cfg.log_level = log_level

    app.config.update(config_overrides)
    app.config['JWT_EXPIRATION_DELTA'] = cfg.jwt_expiration_delta

    ## Configure logging
    app.logger.setLevel(cfg.log_level)

    # Remove standard handlers
    app.logger.handlers = []

    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-40s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # If production mode is activated, set a file logger
    file_handler = logging.handlers.RotatingFileHandler(
        cfg.log_file,
        maxBytes=cfg.log_max_bytes,
        backupCount=cfg.log_n_backups
    )
    file_handler.setFormatter(formatter)
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stdout_handler)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(log_level)
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.addHandler(stdout_handler)
    flask_jwt_logger = logging.getLogger('flask_jwt')
    flask_jwt_logger.setLevel(log_level)
    flask_jwt_logger.addHandler(file_handler)
    flask_jwt_logger.addHandler(stdout_handler)
    tmserver_logger = logging.getLogger('tmserver')
    tmserver_logger.setLevel(log_level)
    tmserver_logger.addHandler(file_handler)
    tmserver_logger.addHandler(stdout_handler)
    wsgi_logger = logging.getLogger('wsgi')
    wsgi_logger.setLevel(log_level)
    wsgi_logger.addHandler(file_handler)
    wsgi_logger.addHandler(stdout_handler)
    tmlib_logger = logging.getLogger('tmlib')
    tmlib_logger.setLevel(log_level)
    tmlib_logger.addHandler(file_handler)
    tmlib_logger.addHandler(stdout_handler)
    gc3pie_logger = logging.getLogger('gc3.gc3libs')
    gc3pie_logger.setLevel(logging.WARN)
    gc3pie_logger.addHandler(file_handler)
    gc3pie_logger.addHandler(stdout_handler)
    apscheduler_logger = logging.getLogger('apscheduler')
    apscheduler_logger.setLevel(logging.CRITICAL)
    apscheduler_logger.addHandler(file_handler)
    apscheduler_logger.addHandler(stdout_handler)

    ## Set the JSON encoder
    app.json_encoder = TmJSONEncoder

    if not cfg.secret_key:
        app.logger.critical('Specify a secret key for this application!')
        sys.exit(1)
    if cfg.secret_key == 'default_secret_key':
        app.logger.warn('The application will run with the default secret key!')
    app.config['SECRET_KEY'] = cfg.secret_key

    ## Initialize Plugins
    jwt.init_app(app)
    redis_store.init_app(app)

    # Create a session scope for interacting with the main database
    engine = create_db_engine(cfg.db_uri_sqla)
    session_factory = create_db_session_factory(engine)
    session = flask_scoped_session(session_factory, app)

    from tmserver.extensions import gc3pie
    gc3pie.init_app(app)

    ## Import and register blueprints
    from api import api
    app.register_blueprint(api, url_prefix='/api')

    from jtui.api import jtui
    # from tmserver.extensions import websocket
    # websocket.init_app(app)
    app.register_blueprint(jtui, url_prefix='/jtui')

    # @app.after_request
    # def after_request(response):
    #   response.headers.add('Access-Control-Allow-Origin', '*')
    #   response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    #   response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    #   return response

    return app
