from logging import getLogger
from threading import Thread, Lock, Event
from requests import post, get
from time import sleep
from .const import pms_header, companion_header, TIMELINE_STOPPED, TIMELINE_PLAYING


class SubscriptionManager:
    def __init__(self, config, play_mgr):
        self.log = getLogger('SubscriptionManager')
        self.sub_lock = Lock()
        self.subscribers = {}
        self.run = Event()
        self.config = config
        self.play_mgr = play_mgr
        self.is_playing = False
        self.last_params = {}
        self.stop_server_notification = True    # signal stop once
        self.stop_send_to_web = True            # signal stop once
        self.notify_thread = Thread(target=self.notify_run, daemon=True)
        self.notify_thread.start()

    @staticmethod
    def dct_to_str(dct):
        s = ''
        for item in dct.items():
            s += item[0] + '="' + str(item[1]) + '" '
        return s[:-1]

    def msg(self):
        state = self.play_mgr.get_state_dct()
        if state:
            state.update({'itemType': 'music'})
            state_str = self.dct_to_str(state)
            xml = TIMELINE_PLAYING.format(parameters=state_str, command_id='{command_id}')
            self.is_playing = True
            self.stop_send_to_web = False
        else:
            xml = TIMELINE_STOPPED
            self.is_playing = False
        return xml

    def update_command_id(self, uuid, command_id):
        with self.sub_lock:
            if command_id and self.subscribers.get(uuid):
                self.subscribers[uuid].command_id = int(command_id)

    def stop(self):
        self.run.set()
        self.notify_thread.join()

    def notify_run(self):
        while not self.run.is_set():
            self.notify()
            sleep(self.config.notify_interval)

    def notify(self):
        with self.sub_lock:
            self.notify_server()
            if self.subscribers:
                msg = self.msg()
                for subscriber in list(self.subscribers.values()):
                    subscriber.send_update(msg)

    def notify_server(self):
        params = self.play_mgr.get_pms_state()
        if params:
            params.update(pms_header(self.config))
            if params['state'] == 'stopped':
                if not self.stop_server_notification:
                    self.log.info('Send stop notification to PMS')
                    self.stop_server_notification = True
                    self.last_params['state'] = 'stopped'
                    self.send_pms_notification(self.last_params)
            else:
                self.stop_server_notification = False
                self.send_pms_notification(params)
                self.last_params = params

    def send_pms_notification(self, params):
        url = self.play_mgr.get_current_pms_timeline()
        get(url, params)
        self.log.debug('Send PMS notification: %s to %s', params, url)

    def add_subscriber(self, protocol, host, port, uuid, command_id):
        subscriber = Subscriber(protocol, host, port, uuid, command_id, self)
        with self.sub_lock:
            self.subscribers[subscriber.uuid] = subscriber
            self.log.debug('Add or update subscriber: %s', host)
        return subscriber

    def remove_subscriber(self, uuid):
        # only called from notify() which already acquired the lock
        for subscriber in list(self.subscribers.values()):
            if subscriber.uuid == uuid or subscriber.host == uuid:
                self.log.debug('Remove subscriber: %s', subscriber.host)
                del self.subscribers[subscriber.uuid]


class Subscriber:
    def __init__(self, protocol, host, port, uuid, command_id, sub_mgr):
        self.log = getLogger('Subscriber')
        self.protocol = protocol
        self.host = host
        self.port = port
        self.uuid = uuid or host
        self.command_id = int(command_id) or 0
        self.sub_mgr = sub_mgr

    def __eq__(self, other):
        return self.uuid == other.uuid

    def send_update(self, msg):
        msg = msg.format(command_id=self.command_id)
        url = '%s://%s:%s/:/timeline' % (self.protocol, self.host, self.port)
        try:
            response = post(url, msg, headers=companion_header(self.sub_mgr.config), timeout=2)
            self.log.debug('Send update to subscriber: %s to %s', msg, self.host)
        except Exception as e:
            self.log.error('Could not send update to subscriber: ' + str(e))
            self.sub_mgr.remove_subscriber(self.uuid)
        else:
            if response.status_code in (False, None, 401):
                self.log.error('Could not send update to subscriber, response code: ' + str(response.status_code))
                self.sub_mgr.remove_subscriber(self.uuid)
