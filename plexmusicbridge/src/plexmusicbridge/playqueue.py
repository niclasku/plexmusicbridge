from logging import getLogger
from random import randint


class PlayQueue:
    def __init__(self):
        self.log = getLogger('PlayQueue')
        self.dct = None
        self.played = []
        self.previous = []
        self.position = 0
        self.current_key = ''
        self.shuffle = False
        self.repeat = 0

    def set_repeat(self, repeat):
        self.repeat = repeat

    def set_shuffle(self, shuffle):
        self.shuffle = bool(shuffle)

    def get_repeat(self):
        return self.repeat

    def get_shuffle(self):
        return int(self.shuffle)

    def get_random_pos(self):
        positions = range(self.get_length())
        positions = [pos for pos in positions if self.get_rating_key(pos) not in self.played]
        i = randint(0, len(positions) - 1)
        return positions[i]

    def set_pos(self, key):
        path = key.split('/')
        self.position = self.get_position(path[-1])

    def next_pos(self, auto):
        if self.shuffle:
            if len(self.played) < self.get_length():
                if self.repeat != 1 or not auto:
                    self.position = self.get_random_pos()
                return True
            elif len(self.played) == self.get_length():
                if self.repeat == 1 and auto:
                    return True
                elif self.repeat == 2:
                    self.played = []
                    self.position = self.get_random_pos()
                    return True
                else:
                    return False
            else:
                self.log.error('Unknown state to get the next track (shuffled)')
                return False
        else:
            if self.position + 1 < self.get_length():
                if self.repeat != 1 or not auto:
                    self.position += 1
                return True
            elif self.position + 1 == self.get_length():
                if self.repeat == 1 and auto:
                    return True
                elif self.repeat == 2:
                    self.played = []
                    self.position = 0
                    return True
                else:
                    return False
            else:
                self.log.error('Unknown state to get the next track')
                return False

    def prev_pos(self):
        if self.shuffle:
            if len(self.previous) > 1:
                self.position = self.get_position(self.previous.pop())
                self.position = self.get_position(self.previous.pop())
        else:
            if self.position > 0:
                self.position -= 1

    def update(self, dct, refresh):
        self.dct = dct
        if refresh:
            self.position = self.get_position(self.current_key)
        else:
            self.position = self.get_selected_item_off()
            self.current_key = self.get_rating_key()
        self.log.info('Current position: ' + str(self.position))
        self.log.info('Current play queue: ' + str(self))

    def is_empty(self):
        return True if self.dct is None else False

    def get_track_info(self):
        return {
            'duration': self.get_duration(),
            'key': self.get_key(),
            'ratingKey': self.get_rating_key(),
            'containerKey': '/playQueues/' + self.get_pq_id(),
            'playQueueID': self.get_pq_id(),
            'playQueueVersion': self.get_pq_version(),
            'playQueueItemID': self.get_pq_item_id()
        }

    def reset(self):
        self.played = []
        self.previous = []
        self.position = 0

    def get_track(self):
        self.current_key = self.get_rating_key()
        if self.current_key not in self.played:
            self.played.append(self.current_key)
        if len(self.previous) > 0 and self.previous[-1] != self.current_key:
            self.previous.append(self.current_key)
        elif len(self.previous) == 0:
            self.previous.append(self.current_key)
        return self.get_url()

    def get_url(self):
        tracks = self.get_track_list()
        return tracks[self.position]['Media']['Part']['@key']

    def get_thumb(self):
        tracks = self.get_track_list()
        return tracks[self.position]['@thumb']

    def get_pq_id(self):
        return self.dct['MediaContainer']['@playQueueID']

    def get_pq_version(self):
        return self.dct['MediaContainer']['@playQueueVersion']

    def get_selected_item_off(self):
        return int(self.dct['MediaContainer']['@playQueueSelectedItemOffset'])

    def get_rating_key(self, position=None):
        tracks = self.get_track_list()
        if position:
            return tracks[position]['@ratingKey']
        else:
            return tracks[self.position]['@ratingKey']

    def get_key(self):
        tracks = self.get_track_list()
        return tracks[self.position]['@key']

    def get_duration(self):
        tracks = self.get_track_list()
        return tracks[self.position]['@duration']

    def get_pq_item_id(self):
        tracks = self.get_track_list()
        return tracks[self.position]['@playQueueItemID']

    def get_length(self):
        return int(self.dct['MediaContainer']['@size'])

    def get_position(self, rating_key):
        for i, track in enumerate(self.get_track_list()):
            if track['@ratingKey'] == rating_key:
                return i
        self.log.error('Could not find track position: ' + rating_key)
        self.log.error('Current play queue: ' + str(self))

    def get_track_list(self):
        if int(self.dct['MediaContainer']['@playQueueTotalCount']) > 1:
            return self.dct['MediaContainer']['Track']
        else:
            return [self.dct['MediaContainer']['Track']]

    def __str__(self):
        s = '\n'
        for pos, track in enumerate(self.get_track_list()):
            s += str(pos) + ': ' + track['@title'] + ' [' + track['@ratingKey'] + ']\n'
        return s[:-1]
