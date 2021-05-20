import vlc
from threading import Thread, Event, Lock
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
        self.log = getLogger('VLCPlayer')
        self.stop_thread = Event()
        self.lock = Lock()
        self.request_next = False
        self.media_player = vlc.MediaPlayer()
        self.manager = manager
        self.monitor_thread = Thread(target=self.monitor, daemon=True)

    def start(self):
        self.monitor_thread.start()

    def play(self, track_url, thumb_url):
        with self.lock:
            self.log.info('Play: ' + track_url)
            media = self.media_player.get_instance().media_new(track_url)
            self.media_player.set_media(media)
            self.media_player.play()
            while not self.media_player.is_playing():
                sleep(0.05)
            self.request_next = True

    def stop(self):
        self.media_player.stop()
        with self.lock:
            self.request_next = False

    def pause(self):
        self.media_player.pause()

    def resume(self):
        self.media_player.play()

    def seek(self, time):
        self.media_player.set_time(time)

    def get_elapsed(self):
        try:
            return self.media_player.get_time()
        except Exception as e:
            self.log.error('Could not get elapsed time: ' + str(e))
            return 0

    def is_muted(self):
        return False

    def set_volume(self, volume):
        self.media_player.audio_set_volume(volume)

    def get_volume(self):
        return self.media_player.audio_get_volume()

    def kill(self):
        self.stop()
        self.stop_thread.set()
        self.monitor_thread.join()

    def is_waiting(self):
        with self.lock:
            if self.request_next and not self.media_player.is_playing():
                self.request_next = False
                return True
            else:
                return False

    def monitor(self):
        while not self.stop_thread.is_set():
            if self.is_waiting():
                self.log.debug('Request next song')
                self.manager.auto_next()
            sleep(0.3)

    def is_ready(self):
        return True

    def wait_for_ready(self):
        return
