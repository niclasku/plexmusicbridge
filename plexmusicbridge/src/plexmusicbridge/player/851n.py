import xmltodict
from urllib.request import urlopen
from urllib.request import Request
from urllib.error import URLError
from logging import getLogger
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread, Lock, Event
from time import sleep
from os import environ

PAYLOAD_FMT = '<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ' \
              's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} xmlns:u="{urn}">' \
              '{fields}</u:{action}></s:Body></s:Envelope>'
AV_URN = 'urn:schemas-upnp-org:service:AVTransport:1'
CONTROL_URL = '/e3f7d9db-2db9-49c7-8958-cc8a98154526/AVTransport/invoke'
EVENT_URL = '/e3f7d9db-2db9-49c7-8958-cc8a98154526/AVTransport/event'
VOL_URN = 'urn:UuVol-com:service:UuVolControl:5'
VOL_URL = '/e3f7d9db-2db9-49c7-8958-cc8a98154526/RecivaRadio/invoke'
REND_URN = 'urn:schemas-upnp-org:service:RenderingControl:1'
REND_URL = '/e3f7d9db-2db9-49c7-8958-cc8a98154526/RenderingControl/invoke'

# hack to set the correct thumbnail
# rest of metadata is not used by device but necessary to send
META_DATA_FMT = '&lt;DIDL-Lite xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot; ' \
                'xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; ' \
                'xmlns:dlna=&quot;urn:schemas-dlna-org:metadata-1-0/&quot;&gt;&lt;item id=&quot;23$45076$@45077&quot; '\
                'parentID=&quot;23$45076&quot; restricted=&quot;1&quot;&gt;&lt;dc:title ' \
                'xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot;&gt;Keeping The ' \
                'Faith&lt;/dc:title&gt;&lt;upnp:class ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;object.item.audioItem.musicTrack' \
                '&lt;/upnp:class&gt;&lt;dc:date ' \
                'xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot;&gt;1991-01-01&lt;/dc:date&gt;&lt;upnp:album ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;1991&lt;/upnp:album&gt;&lt;upnp' \
                ':artist xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;Lynyrd ' \
                'Skynyrd&lt;/upnp:artist&gt;&lt;dc:creator ' \
                'xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot;&gt;Lynyrd ' \
                'Skynyrd&lt;/dc:creator&gt;&lt;upnp:genre ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;Southern ' \
                'Rock&lt;/upnp:genre&gt;&lt;upnp:originalTrackNumber ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;2&lt;/upnp:originalTrackNumber&gt' \
                ';&lt;upnp:albumArtURI xmlns:dlna=&quot;urn:schemas-dlna-org:metadata-1-0/&quot; ' \
                'dlna:profileID=&quot;JPEG_TN&quot; ' \
                'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;{}&lt;/upnp:albumArtURI&gt;&lt;res '\
                'bitrate=&quot;112875&quot; duration=&quot;0:05:19.000&quot; nrAudioChannels=&quot;2&quot; ' \
                'protocolInfo=&quot;http-get:*:audio/x-flac:*&quot; sampleFrequency=&quot;44100&quot; ' \
                'size=&quot;36126766&quot;&gt;http://192.168.10.2:50002/m/NDLNA/45077.flac&lt;/res&gt;&lt;/item&gt' \
                ';&lt;/DIDL-Lite&gt; '


def unescape_xml(xml):
    return xml.decode().replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')


class PlayerConfig:
    def __init__(self):
        self.ip = None
        self.port = None
        self.host_ip = None
        self.notify_port = None
        self.rewrite_http = True
        self.rewrite_host = False

    def parse_env(self):
        self.ip = environ.get('PLAYER_IP')
        self.port = environ.get('PLAYER_PORT') or '8050'
        self.host_ip = environ.get('HOST_IP')
        self.notify_port = environ.get('NOTIFY_PORT') or '30111'
        self.rewrite_host = self.host_ip

    def save_arguments(self, args):
        self.ip = args.player_ip
        self.port = args.player_port or '8050'
        self.host_ip = args.player_host_ip
        self.notify_port = args.player_notify_port or '30111'
        self.rewrite_host = args.player_host_ip

    @staticmethod
    def add_arguments(parser):
        parser.add_argument('--player_ip', help='IP of 851N', required=True)
        parser.add_argument('--player_port', help='Port of 851N')
        parser.add_argument('--host_ip', help='IP of the host running this service', required=True)
        parser.add_argument('--notify_port', help='UPnP notification port')


class Player:
    def __init__(self, manager, config):
        self.log = getLogger('851N')
        self.ip = config.player.ip
        self.port = config.player.port
        self.host_ip = config.player.host_ip
        self.notify_port = config.player.notify_port

        self.lock = Lock()
        self.action = 'stop'
        self.request_next = False
        self.is_paused = False
        self.manager = manager

        self.stop_signal = Event()
        self.monitor_thread = Thread(target=self.monitor, daemon=True)
        self.notify_server = NotificationServer(self, ('0.0.0.0', int(self.notify_port)), NotificationHandler)
        self.notify_server_thread = Thread(target=self.notify_server.serve_forever, daemon=True)
        self.subscription_thread = Thread(target=self._renew_subscription, daemon=True)

    def start(self):
        self.monitor_thread.start()
        self.notify_server_thread.start()
        self.subscription_thread.start()

    def _renew_subscription(self):
        while 1:
            self._subscribe()
            x = 0
            while x < 1200:
                if self.stop_signal.is_set():
                    return
                x = x + 1
                sleep(0.1)

    def _subscribe(self):
        soap_url = 'http://{}:{}{}'.format(self.ip, self.port, EVENT_URL)
        headers = {
            'Cache-Control': 'no-cache',
            'User-Agent': '{}/{}'.format(__file__, '1.0'),
            'NT': 'upnp:event',
            'Callback': '<http://' + self.host_ip + ':' + self.notify_port + '>',
            'Timeout': 'Second-3600'
        }
        req = Request(soap_url, headers=headers, method='SUBSCRIBE')
        res = urlopen(req, timeout=5)
        if res.code == 200:
            return True
        return False

    @staticmethod
    def _payload_from_template(action, data, urn):
        fields = ''
        for item in data:
            for tag, value in item.items():
                fields += '<{tag}>{value}</{tag}>'.format(tag=tag, value=value)
        payload = PAYLOAD_FMT.format(action=action, urn=urn, fields=fields)
        return payload

    def _soap_request(self, action, data, url=CONTROL_URL, urn=AV_URN):
        self.log.info('SOAP Request: ' + str(action))
        soap_url = 'http://{}:{}{}'.format(self.ip, self.port, url)
        headers = {
            'Content-type': 'text/xml',
            'SOAPACTION': '"{}#{}"'.format(urn, action),
            'charset': 'utf-8',
            'User-Agent': '{}/{}'.format(__file__, '1.0')
        }
        payload = self._payload_from_template(action=action, data=data, urn=urn)
        try:
            req = Request(soap_url, data=payload.encode(), headers=headers)
            res = urlopen(req, timeout=5)
            if res.code == 200:
                data = res.read()
                response = xmltodict.parse(unescape_xml(data))
                try:
                    error = response['s:Envelope']['s:Body']['s:Fault']['detail']['UPnPError']['errorDescription']
                    self.log.error('SOAP request returned error: ' + str(error))
                    return None
                except (TypeError, KeyError):
                    return response
        except Exception as e:
            self.log.error('SOAP request failed: ' + str(e))

    def _position_info(self, instance_id=0):
        response = self._soap_request('GetPositionInfo', [{'InstanceID': instance_id}])
        if response:
            return dict(response['s:Envelope']['s:Body']['r:GetPositionInfoResponse'])
        else:
            return None

    def _check_response(self, response, name):
        try:
            if response['s:Envelope']['s:Body'][name] is not None:
                return True
            else:
                return False
        except (TypeError, KeyError):
            self.log.error('SOAP request failed')
            return False

    def _set_current_media(self, media_url, thumb_url='http://via.placeholder.com/350x350'):
        metadata = META_DATA_FMT.format(thumb_url)
        response = self._soap_request('SetAVTransportURI', [
            {'InstanceID': 0},
            {'CurrentURI': media_url},
            {'CurrentURIMetaData': metadata}
        ])
        return self._check_response(response, 'u:SetAVTransportURIResponse')

    def _play(self, speed=1):
        response = self._soap_request('Play', [{'InstanceID': 0}, {'Speed': speed}])
        return self._check_response(response, 'u:PlayResponse')

    def _get_source(self):
        response = self._soap_request('GetAudioSource', urn=VOL_URN, data=[{'InstanceID': 0}], url=VOL_URL)
        try:
            return response['s:Envelope']['s:Body']['r:GetAudioSourceResponse']['RetAudioSourceValue'].lower()
        except (TypeError, KeyError):
            return 'media player'

    def play(self, music, thumb):
        with self.lock:
            self.log.debug('Play: ' + music + ' with thumbnail ' + thumb)
            self._set_current_media(music, thumb_url=thumb)
            self._play()
            while self.action != 'play':
                sleep(0.2)
            self.request_next = True
            self.is_paused = False

    def pause(self):
        with self.lock:
            self.is_paused = True
            response = self._soap_request('Pause', [{'InstanceID': 0}, {'Speed': 1}])
        return self._check_response(response, 'r:PauseResponse')

    def stop(self):
        with self.lock:
            self.request_next = False
            response = self._soap_request('Stop', [{'InstanceID': 0}, {'Speed': 1}])
        return self._check_response(response, 'r:StopResponse')

    def resume(self):
        with self.lock:
            self.is_paused = False
            return self._play()

    def seek(self, position):
        secs = int(round(position / 1000))
        hour = int(secs / 3600)
        minute = int((secs / 60) % 60)
        second = int(secs - (hour * 3600) - (minute * 60))
        position = str(hour) + ':' + str(minute).zfill(2) + ':' + str(second).zfill(2)
        response = self._soap_request('Seek', [{'InstanceID': 0}, {'Unit': 'REL_TIME'}, {'Target': position}])
        return self._check_response(response, 'r:SeekResponse')

    def get_elapsed(self):
        info = self._position_info()
        if info is not None:
            t = info['RelTime'].split(':')
            return (int(t[0]) * 3600 + int(t[1]) * 60 + int(t[2])) * 1000
        return 0

    def is_muted(self):
        data = [{'InstanceID': 0}, {'Channel': 'Master'}]
        response = self._soap_request('GetMute', urn=REND_URN, data=data, url=REND_URL)
        try:
            mute = int(response['s:Envelope']['s:Body']['r:GetMuteResponse']['CurrentMute'])
            if mute == 0:
                return False
            else:
                return True
        except (TypeError, KeyError):
            return False

    def set_volume(self, volume):
        vol = int(round(int(volume), -1) / 10)
        data = [{'InstanceID': 0}, {'Channel': 'Master'}, {'DesiredVolume': vol}]
        response = self._soap_request('SetVolume', urn=REND_URN, data=data, url=REND_URL)
        return self._check_response(response, 'SetVolumeResponse')

    def get_volume(self):
        data = [{'InstanceID': 0}, {'Channel': 'Master'}]
        response = self._soap_request('GetVolume', urn=REND_URN, data=data, url=REND_URL)
        try:
            vol = int(response['s:Envelope']['s:Body']['r:GetVolumeResponse']['CurrentVolume'])
            if vol <= 10:
                return vol * 10
            else:
                return 100
        except (TypeError, KeyError):
            return 0

    def is_waiting(self):
        if self.action == 'pause' and self.is_paused is False:
            return True
        else:
            return False

    def monitor(self):
        n = 0
        while not self.stop_signal.is_set():
            if self.is_waiting() and self.request_next:
                self.log.info('Detected end of song, play next one')
                self.manager.auto_next()
            if n == 3:
                if self.request_next and self._get_source() != 'media player':
                    self.log.info('Stop playback because player changed source')
                    self.manager.stop()
                n = 0
            else:
                n += 1
            sleep(0.5)

    def is_ready(self):
        url = 'http://{}'.format(self.ip)
        try:
            urlopen(url)
            return True
        except URLError:
            return False

    def wait_for_ready(self):
        while not self.is_ready():
            sleep(2)

    def kill(self):
        self.stop_signal.set()
        self.stop()
        self.notify_server.shutdown()
        self.notify_server.server_close()
        self.notify_server_thread.join()
        self.subscription_thread.join()
        self.monitor_thread.join()


class NotificationServer(HTTPServer):
    def __init__(self, device, *args, **kw):
        HTTPServer.__init__(self, *args, **kw)
        self.log = getLogger('851N NotificationServer')
        self.device = device


class NotificationHandler(BaseHTTPRequestHandler):
    def do_NOTIFY(self):
        self.send_response(200)
        data = self.rfile.read(int(self.headers.get('content-length')))
        response = xmltodict.parse(unescape_xml(data))
        try:
            current_state = str(response['e:propertyset']['e:property']['LastChange']['Event']['InstanceID']
                                ['TransportState']['@val'])
            if current_state == 'PLAYING':
                self.server.device.action = 'play'
            elif current_state == 'STOPPED':
                self.server.device.action = 'stop'
            elif current_state == 'NO_MEDIA_PRESENT':
                self.server.device.action = 'stop'
            elif current_state == 'PAUSED_PLAYBACK':
                self.server.device.action = 'pause'
            elif current_state == 'TRANSITIONING':
                self.server.device.action = 'transition'
        except Exception as e:
            self.server.log.error('Could not parse notification: ' + str(e))
            pass

    def log_message(self, fmt, *args):
        return
