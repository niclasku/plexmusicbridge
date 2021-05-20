import logging
from logging.handlers import TimedRotatingFileHandler
from .plexgdm import PlexGdm
from .httpserver import HTTPServer
from .subscriptionmanager import SubscriptionManager
from .playbackmanager import PlaybackManager
from os import environ, path
from .config import Config
from argparse import ArgumentParser
from importlib import import_module


def init_logging(log_path, level):
    log_file = log_path + 'log.txt'
    log_format = '%(asctime)s - [%(levelname)s] %(name)s: %(message)s'
    logging.basicConfig(level=level, format=log_format)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logger = logging.getLogger()
    rollover = path.isfile(log_file)
    handler = TimedRotatingFileHandler(filename=log_file, backupCount=5, when='d', interval=1)
    handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(handler)
    if rollover:
        handler.doRollover()


def parse_config():
    if environ.get('PLAYER_NAME'):
        player_name = environ.get('PLAYER_NAME')
        log = environ.get('LOG_PATH')
        gdm = environ.get('GDM_PORT')
        companion = environ.get('COMPANION_PORT')
        title = environ.get('TITLE')
        subtitle = environ.get('SUBTITLE')
        level = environ.get('LOG_LEVEL')
        notify_interval = environ.get('NOTIFY_INTERVAL')
        gdm_interval = environ.get('GDM_INTERVAL')
        player_module = import_module('.player.' + player_name, package='plexmusicbridge')
        player_config = getattr(player_module, 'PlayerConfig')()
        player_config.parse_env()
        config = Config(player_name, player_config, log, gdm, companion, title, subtitle, notify_interval, gdm_interval)
    else:
        parser = ArgumentParser(description='PlexMusicBridge')
        parser.add_argument('-p', '--player_name', help='Player file name', required=True)
        parser.add_argument('-g', '--gdm', help='GDM Port')
        parser.add_argument('-c', '--companion', help='Companion Port')
        parser.add_argument('-t', '--title', help='Title propagated to all Plex apps')
        parser.add_argument('-s', '--subtitle', help='Subtitle propagated to all Plex apps')
        parser.add_argument('-l', '--log', help='Path to log files')
        parser.add_argument('--log_level', help='Log level (debug, info, warning, error)')
        parser.add_argument('--notify_interval', help='Interval of sending play state notifications to all Plex '
                                                      'apps')
        parser.add_argument('--gdm_interval', help='Interval of sending GDM messages')
        args = parser.parse_known_args()[0]
        player_module = import_module('.player.' + args.player_name, package='plexmusicbridge')
        player_config = getattr(player_module, 'PlayerConfig')()
        player_config.add_arguments(parser)
        args = parser.parse_args()
        player_config.save_arguments(args)
        level = args.log_level
        config = Config(args.player_name, player_config, args.log, args.gdm, args.companion, args.title, args.subtitle,
                        args.notify_interval, args.gdm_interval)

    if level == 'debug':
        level = logging.DEBUG
    elif level == 'info':
        level = logging.INFO
    elif level == 'warning':
        level = logging.WARNING
    else:
        level = logging.ERROR

    return config, level


def main():
    config, debug_lvl = parse_config()
    init_logging(config.log_path, debug_lvl)
    log = logging.getLogger('Main')

    log.info('Startup')
    # init good day mate protocol
    gdm = PlexGdm(config)
    while True:
        # init
        pl = PlaybackManager(config)
        sub = SubscriptionManager(config, pl)
        http = HTTPServer(config, sub, pl)

        # wait for the player to become ready
        log.info('Waiting for player')
        pl.wait_for_ready()
        gdm.start()
        pl.start()

        # run as long as player is ready
        while pl.is_ready():
            from time import sleep
            sleep(2)

        log.info('Player is offline -> restart')
        # shutdown
        gdm.stop()
        sub.stop()
        http.stop()
        pl.kill()
