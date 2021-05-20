from time import sleep
from logging import getLogger


class PlayerConfig:
    def __init__(self):
        self.rewrite_http = False
        self.rewrite_host = False

    def parse_env(self):
        pass

    def save_arguments(self, args):
        pass

    @staticmethod
    def add_arguments(parser):
        pass


class Player:
    def __init__(self, manager, config):
        self.log = getLogger('Player')
        # e.g. playback manager can be used to signal end of a track
        self.manager = manager
        self.config = config.player

    def start(self):
        # called on startup
        pass

    def play(self, track_url, thumb_url):
        # play file
        pass

    def stop(self):
        # stop playback
        pass

    def pause(self):
        # pause playback
        pass

    def resume(self):
        # resume playback
        pass

    def seek(self, time):
        # seek to given time in ms
        pass

    def get_elapsed(self):
        # return elapsed time in ms
        return 0

    def is_muted(self):
        # return if player is muted
        return False

    def set_volume(self, volume):
        # set volume to given value
        pass

    def get_volume(self):
        # return current volume
        return 0

    def kill(self):
        # kill all threads and stop playback
        self.stop()

    def is_ready(self):
        # returns True if player is ready to play
        return True

    def wait_for_ready(self):
        while not self.is_ready():
            sleep(1)
