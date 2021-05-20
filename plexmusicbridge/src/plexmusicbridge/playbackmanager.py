from logging import getLogger
from .plexserver import PlexServer
from importlib import import_module
from .playqueue import PlayQueue
from threading import Lock


class PlaybackManager:
    """
    Only place to access player and play queue because this needs to be thread safe
    """
    def __init__(self, config):
        self.log = getLogger('PlayBackManager')
        self.config = config
        # play queue
        self.queue_lock = Lock()
        self.queue = PlayQueue()
        # plex server
        self.plex_lock = Lock()
        self.plex_server = PlexServer()
        # player
        self.player_lock = Lock()
        player_module = import_module('.player.' + config.player_name, package='plexmusicbridge')
        self.player = getattr(player_module, 'Player')(self, config)
        # variables
        self.lock = Lock()
        self.is_playing = False
        self.is_paused = False
        self.last_cmd_id = {}

    def start(self):
        with self.player_lock:
            self.player.start()

    def get_play_state(self):
        with self.lock:
            return self.is_playing

    def get_state_dct(self):
        self.lock.acquire()
        if self.is_playing:
            self.lock.release()
            with self.queue_lock:
                track_info = self.queue.get_track_info()
                shuffle = self.queue.get_shuffle()
                repeat = self.queue.get_repeat()
            with self.plex_lock:
                server_info = self.plex_server.get_info()
            with self.player_lock:
                elapsed = self.player.get_elapsed()
                volume = self.player.get_volume()
                muted = int(self.player.is_muted())
            state = {
                'time': elapsed,
                'volume': volume,
                'mute': muted,
                'state': self.get_state(),
                'shuffle': shuffle,
                'repeat': repeat
            }
            state.update(track_info)
            state.update(server_info)
            return state
        else:
            self.lock.release()
            return None

    def get_pms_state(self):
        self.queue_lock.acquire()
        if not self.queue.is_empty():
            rating_key = self.queue.get_rating_key()
            key = self.queue.get_key()
            duration = self.queue.get_duration()
            pq_item_id = self.queue.get_pq_item_id()
            shuffle = self.queue.get_shuffle()
            repeat = self.queue.get_repeat()
            container_key = '/playQueues/' + self.queue.get_pq_id()
            self.queue_lock.release()
            if self.is_playing:
                with self.player_lock:
                    elapsed = self.player.get_elapsed()
            else:
                elapsed = 0
            with self.plex_lock:
                token = self.plex_server.token
            return {
                'state': self.get_state(),
                'ratingKey': rating_key,
                'key': key,
                'time': elapsed,
                'duration': duration,
                'playQueueItemID': pq_item_id,
                'X-Plex-Token': token,
                'shuffle': shuffle,
                'repeat': repeat,
                'containerKey': container_key
            }
        else:
            self.queue_lock.release()
            return None

    def get_current_pms_timeline(self):
        with self.plex_lock:
            return self.plex_server.build_url('/:/timeline', False)

    def get_state(self):
        with self.lock:
            if self.is_playing and self.is_paused:
                return 'paused'
            elif self.is_playing and not self.is_paused:
                return 'playing'
            else:
                return 'stopped'

    def handle_cmd(self, address, path, opt):
        # try to update server info
        with self.plex_lock:
            self.plex_server.update(opt)

        # check if we receive a command twice by comparing host and last command id
        with self.lock:
            try:
                if self.last_cmd_id[address[0]] == opt['commandID']:
                    self.log.info('Detected same command id -> skip this command')
                    return
            except KeyError:
                pass
            self.last_cmd_id[address[0]] = opt['commandID']

        if path == '/player/playback/playMedia':
            self.play_media(opt['type'], opt['containerKey'])
        elif path == '/player/playback/refreshPlayQueue':
            self.update_queue('/playQueues/' + opt['playQueueID'])
        elif path == '/player/playback/seekTo':
            with self.player_lock:
                self.player.seek(int(opt['offset']))
        elif path == '/player/playback/pause':
            self.pause()
        elif path == '/player/playback/play':
            self.play()
        elif path == '/player/playback/stop':
            self.stop()
        elif path == '/player/playback/skipNext':
            self.next()
        elif path == '/player/playback/skipPrevious':
            self.previous()
        elif path == '/player/playback/skipTo':
            self.skip(opt['key'])
        elif path == '/player/playback/setParameters':
            if opt.get('repeat'):
                with self.queue_lock:
                    self.queue.set_repeat(int(opt['repeat']))
            elif opt.get('volume'):
                with self.player_lock:
                    self.player.set_volume(int(opt['volume']))
            elif opt.get('shuffle'):
                with self.queue_lock:
                    self.queue.set_shuffle(int(opt['shuffle']))
            else:
                self.log.warning('Not implemented: ' + opt)
        else:
            self.log.warning('Not implemented: ' + path)

    def update_queue(self, container_key):
        with self.plex_lock:
            pq = self.plex_server.get_queue(container_key)
        with self.queue_lock:
            self.queue.update(pq, True)

    def play_media(self, media_type, container_key):
        if media_type != 'music':
            self.log.error('Items in the queue are not of type music')
            self.stop()
        else:
            with self.plex_lock:
                pq = self.plex_server.get_queue(container_key)
            with self.queue_lock:
                self.queue.reset()
                self.queue.update(pq, False)
            self.play()

    def load_play(self):
        with self.queue_lock:
            track = self.queue.get_track()
            thumb = self.queue.get_thumb()
        with self.plex_lock:
            track_url = self.plex_server.build_url(track,
                                                   rewrite_http=self.config.player.rewrite_http,
                                                   rewrite_host=self.config.player.rewrite_host)
            thumb_url = self.plex_server.build_url(thumb,
                                                   rewrite_http=self.config.player.rewrite_http,
                                                   rewrite_host=self.config.player.rewrite_host)
        with self.player_lock:
            self.player.play(track_url, thumb_url)

    def play(self):
        self.lock.acquire()
        if self.is_paused and self.is_playing:
            self.is_playing = True
            self.is_paused = False
            self.lock.release()
            with self.player_lock:
                self.player.resume()
        elif self.is_playing and not self.is_paused:
            self.is_playing = True
            self.is_paused = False
            self.lock.release()
            self.load_play()
        elif not self.is_playing:
            self.is_playing = True
            self.is_paused = False
            self.lock.release()
            self.load_play()

    def pause(self):
        self.lock.acquire()
        if not self.is_paused:
            self.is_paused = True
            self.lock.release()
            with self.player_lock:
                self.player.pause()

    def skip(self, key):
        with self.queue_lock:
            self.queue.set_pos(key)
        self.play()

    def stop(self):
        with self.lock:
            self.is_playing = False
            self.is_paused = False
        with self.queue_lock:
            self.queue.reset()
        with self.player_lock:
            self.player.stop()

    def auto_next(self):
        with self.queue_lock:
            ret = self.queue.next_pos(True)
        if ret:
            self.play()
        else:
            self.stop()

    def next(self):
        with self.queue_lock:
            ret = self.queue.next_pos(False)
        if ret:
            self.play()
        else:
            self.stop()

    def previous(self):
        with self.queue_lock:
            self.queue.prev_pos()
        self.play()

    def kill(self):
        with self.player_lock:
            self.player.kill()

    def is_ready(self):
        with self.player_lock:
            return self.player.is_ready()

    def wait_for_ready(self):
        with self.player_lock:
            return self.player.wait_for_ready()
