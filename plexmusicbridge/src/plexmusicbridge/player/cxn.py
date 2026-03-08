import xmltodict
import asyncio
from urllib.request import urlopen
from urllib.request import Request
from logging import getLogger
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread, Lock, Event
from time import sleep, monotonic
from os import environ
from aiostreammagic import StreamMagicClient

PAYLOAD_FMT = '<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ' \
              's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} xmlns:u="{urn}">' \
              '{fields}</u:{action}></s:Body></s:Envelope>'
AV_URN = 'urn:schemas-upnp-org:service:AVTransport:1'
CONTROL_URL = '/d985a16c-c3e8-48a0-9fd1-2f36ab24a78a/AVTransport/invoke'
EVENT_URL = '/d985a16c-c3e8-48a0-9fd1-2f36ab24a78a/AVTransport/event'
REND_URN = 'urn:schemas-upnp-org:service:RenderingControl:1'
REND_URL = '/d985a16c-c3e8-48a0-9fd1-2f36ab24a78a/RenderingControl/invoke'
DEVICE_MAX_VOLUME = 50

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
        self.rewrite_http = False
        self.rewrite_host = False

    def parse_env(self):
        self.ip = environ.get('PLAYER_IP')
        self.port = environ.get('PLAYER_PORT') or '8050'
        self.host_ip = environ.get('HOST_IP')
        self.notify_port = environ.get('NOTIFY_PORT') or '30111'

    def save_arguments(self, args):
        self.ip = args.player_ip
        self.port = args.player_port or '8050'
        self.host_ip = args.host_ip
        self.notify_port = args.notify_port or '30111'

    @staticmethod
    def add_arguments(parser):
        parser.add_argument('--player_ip', help='IP of 851N', required=True)
        parser.add_argument('--player_port', help='Port of 851N')
        parser.add_argument('--host_ip', help='IP of the host running this service', required=True)
        parser.add_argument('--notify_port', help='UPnP notification port')


class Player:
    def __init__(self, manager, config):
        self.log = getLogger('CXN')
        self.ip = config.player.ip
        self.port = config.player.port
        self.host_ip = config.player.host_ip
        self.notify_port = config.player.notify_port

        self.lock = Lock()
        self.action = 'stop'
        self.request_next = False
        self.is_paused = False
        self.last_elapsed = 0
        self.last_known_volume = 50
        self.last_logged_volume = None
        self.bridge_session_active = False
        self.bridge_source = None

        self.sm_lock = Lock()
        self.sm_source = None
        self.sm_state = None
        self.sm_volume_percent = None
        self.sm_last_update = 0.0
        self.sm_client = None
        self.manager = manager

        self.stop_signal = Event()
        self.monitor_thread = Thread(target=self.monitor, daemon=True)
        self.streammagic_thread = Thread(target=self._streammagic_loop, daemon=True)
        self.notify_server = NotificationServer(self, ('0.0.0.0', int(self.notify_port)), NotificationHandler)
        self.notify_server_thread = Thread(target=self.notify_server.serve_forever, daemon=True)
        self.subscription_thread = Thread(target=self._renew_subscription, daemon=True)

    def start(self):
        self._initialize_volume_cache()
        self.streammagic_thread.start()
        self.monitor_thread.start()
        self.notify_server_thread.start()
        self.subscription_thread.start()

    def _initialize_volume_cache(self):
        vol = self._read_volume()
        if vol is not None:
            self.last_known_volume = vol

    async def _update_streammagic_snapshot(self):
        if self.sm_client is None:
            return
        play_state = await self.sm_client.get_play_state()
        state = await self.sm_client.get_state()
        source = None
        if play_state and play_state.metadata:
            source = play_state.metadata.source
        if not source:
            source = state.source if state else None
        new_volume_percent = state.volume_percent if state else None
        bump_timeline = False
        with self.sm_lock:
            prev_volume_percent = self.sm_volume_percent
            self.sm_source = source
            self.sm_state = play_state.state if play_state else None
            self.sm_volume_percent = new_volume_percent
            self.sm_last_update = monotonic()
            if new_volume_percent is not None and prev_volume_percent != new_volume_percent:
                bump_timeline = True
        if bump_timeline:
            self.manager.bump_timeline_id()

    async def _on_streammagic_update(self, _client, _callback_type):
        try:
            await self._update_streammagic_snapshot()
        except Exception as e:
            self.log.debug('StreamMagic callback update failed: %s', e)

    async def _streammagic_runner(self):
        while not self.stop_signal.is_set():
            try:
                self.sm_client = StreamMagicClient(self.ip)
                await self.sm_client.connect()
                await self.sm_client.register_state_update_callbacks(self._on_streammagic_update)
                await self._update_streammagic_snapshot()
                while not self.stop_signal.is_set():
                    # Fallback polling in case push updates are delayed.
                    await self._update_streammagic_snapshot()
                    await asyncio.sleep(2)
            except Exception as e:
                self.log.warning('StreamMagic detector unavailable: %s', e)
                await asyncio.sleep(2)
            finally:
                if self.sm_client is not None:
                    try:
                        await self.sm_client.disconnect()
                    except Exception:
                        pass
                self.sm_client = None

    def _streammagic_loop(self):
        asyncio.run(self._streammagic_runner())

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

    def _is_owned_by_bridge(self):
        with self.sm_lock:
            source = self.sm_source
            last_update = self.sm_last_update

        if monotonic() - last_update > 10:
            # Avoid false positives when detector is temporarily stale.
            self.log.debug('StreamMagic snapshot stale, assuming bridge ownership')
            return True

        if self.bridge_source is None and source:
            self.bridge_source = source

        if self.bridge_source and source and source != self.bridge_source:
            self.log.info('Detected external source change (%s -> %s)', self.bridge_source, source)
            return False

        # Source unchanged means ownership is still ours.
        # We intentionally do not gate on state here to allow end-of-track handling.
        return True

    def play(self, music, thumb):
        with self.lock:
            self.log.debug('Play: ' + music + ' with thumbnail ' + thumb)
            self._set_current_media(music, thumb_url=thumb)
            self._play()
            while self.action != 'play':
                sleep(0.2)
            self.request_next = True
            self.is_paused = False
            self.bridge_session_active = True
            with self.sm_lock:
                self.bridge_source = self.sm_source

    def pause(self):
        with self.lock:
            self.is_paused = True
            response = self._soap_request('Pause', [{'InstanceID': 0}, {'Speed': 1}])
        return self._check_response(response, 'r:PauseResponse')

    def stop(self):
        with self.lock:
            self.request_next = False
            self.bridge_session_active = False
            self.bridge_source = None
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
        vol = int(round((int(volume) * DEVICE_MAX_VOLUME) / 100))
        data = [{'InstanceID': 0}, {'Channel': 'Master'}, {'DesiredVolume': vol}]
        response = self._soap_request('SetVolume', urn=REND_URN, data=data, url=REND_URL)
        if response:
            self.last_known_volume = int(volume)
        return self._check_response(response, 'SetVolumeResponse')

    def _read_volume(self):
        data = [{'InstanceID': 0}, {'Channel': 'Master'}]
        response = self._soap_request('GetVolume', urn=REND_URN, data=data, url=REND_URL)
        try:
            vol = int(response['s:Envelope']['s:Body']['r:GetVolumeResponse']['CurrentVolume'])
            vol = max(0, min(vol, DEVICE_MAX_VOLUME))
            return int(round((vol * 100) / DEVICE_MAX_VOLUME))
        except (TypeError, KeyError):
            return None

    def get_volume(self):
        with self.sm_lock:
            sm_volume_percent = self.sm_volume_percent
        if sm_volume_percent is not None:
            sm_volume_percent = max(0, min(int(sm_volume_percent), 100))
            vol = sm_volume_percent
            self.last_known_volume = vol
            if self.last_logged_volume != vol:
                self.log.info('Volume changed to %s (StreamMagic percent=%s)',
                              vol, sm_volume_percent)
                self.last_logged_volume = vol
                self.manager.bump_timeline_id()
            return vol

        vol = self._read_volume()
        if vol is None:
            return self.last_known_volume
        self.last_known_volume = vol
        if self.last_logged_volume != vol:
            self.log.info('Volume changed to %s (SOAP fallback)', vol)
            self.last_logged_volume = vol
            self.manager.bump_timeline_id()
        return vol

    def is_waiting(self):
        if (self.action == 'pause' or self.action == 'stop') and self.is_paused is False:
            return True
        else:
            return False

    def monitor(self):
        while not self.stop_signal.is_set():
            if self.request_next and self.action == 'play':
                elapsed = self.get_elapsed()
                if elapsed >= 0:
                    self.last_elapsed = elapsed

            if self.is_waiting() and self.request_next:
                if self.bridge_session_active and not self._is_owned_by_bridge():
                    self.log.info('Stop local playback because StreamMagic detected external takeover')
                    self.bridge_session_active = False
                    self.bridge_source = None
                    self.request_next = False
                    self.manager.stop_local()
                else:
                    with self.manager.queue_lock:
                        duration = int(self.manager.queue.get_duration())

                    if duration - self.last_elapsed > 5000:
                        self.log.info('Stop local playback because track stopped before end (%sms/%sms)',
                                      self.last_elapsed, duration)
                        self.bridge_session_active = False
                        self.bridge_source = None
                        self.request_next = False
                        self.manager.stop_local()
                    else:
                        self.log.info('Detected end of song, play next one')
                        self.manager.auto_next()
            sleep(0.5)

    def is_ready(self):
        url = 'http://{}'.format(self.ip)
        try:
            urlopen(url)
            return True
        except:
            return False

    def wait_for_ready(self):
        while not self.is_ready():
            sleep(2)

    def kill(self):
        self.stop_signal.set()
        self.stop()
        self.notify_server.shutdown()
        self.notify_server.server_close()
        self.streammagic_thread.join()
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
