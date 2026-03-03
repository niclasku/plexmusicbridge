from logging import getLogger
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from .const import XML_OK, device_header, resource_xml, web_header
from threading import Thread, Event


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.protocol_version = 'HTTP/1.1'
        self.log = getLogger('HTTPServer')
        SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.log.debug('Serving GET request...')
        self.handle_request()

    def send_resp(self, body, headers=None, code=200):
        headers = {} if headers is None else headers
        try:
            self.send_response(code)
            for key in headers:
                self.send_header(key, headers[key])
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body.encode('utf-8'))
        except Exception as e:
            self.log.error(e)

    def parse_path(self):
        # Parse url into path and parameters
        parsed = urlparse(self.path)
        request_path = parsed.path
        param_array = parse_qs(parsed.query)
        request_params = {}
        for key in param_array:
            request_params[key] = param_array[key][0]
        return request_path, request_params

    def handle_request(self):
        # handle get requests
        request_path, request_params = self.parse_path()
        self.log.info('Request path: ' + request_path)
        self.log.debug('Request parameters: ' + str(request_params))
        self.log.info('Request origin: ' + self.address_string())

        # update command ID for subscriber
        sub_mgr = self.server.sub_mgr
        sub_mgr.update_command_id(self.headers.get('X-Plex-Client-Identifier', self.client_address[0]),
                                  request_params.get('commandID'))

        # check if we can answer the request directly
        if request_path == '/version':
            self.send_resp('UPnP Bridge: Running')

        elif request_path == '/verify':
            self.send_resp('Connection Test: OK')

        elif request_path == '/resources':
            self.send_resp(resource_xml(self.server.config), device_header(self.server.config))

        elif request_path == '/player/timeline/poll':
            self.handle_polling(request_params)

        elif '/subscribe' in request_path:
            self.send_resp(XML_OK, device_header(self.server.config))
            protocol = request_params.get('protocol')
            host = self.client_address[0]
            port = request_params.get('port')
            uuid = self.headers.get('X-Plex-Client-Identifier')
            command_id = request_params.get('commandID', 0)
            sub_mgr.add_subscriber(protocol, host, port, uuid, command_id)

        elif '/unsubscribe' in request_path:
            self.send_resp(XML_OK, device_header(self.server.config))
            uuid = self.headers.get('X-Plex-Client-Identifier') or self.client_address[0]
            sub_mgr.remove_subscriber(uuid)
        elif '/mirror' in request_path:
            self.send_resp('', device_header(self.server.config))
        else:
            # Handle all playback commands
            try:
                self.server.play_mgr.handle_cmd(self.client_address, request_path, request_params)
            except Exception as e:
                self.log.error('Error handling playback command %s: %s', request_path, e)
                self.send_resp('', device_header(self.server.config), code=500)
            else:
                self.send_resp('', device_header(self.server.config))

    def handle_polling(self, request_params):
        from time import sleep, monotonic
        sub_mgr = self.server.sub_mgr
        wait_for_update = request_params.get('wait') == '1'
        client_uuid = self.headers.get('X-Plex-Client-Identifier', self.client_address[0])

        timeline_id = self.server.play_mgr.get_timeline_id()
        last_timeline_id = self.server.timeline_tracker.get(client_uuid, 0)

        # Plexamp expects long-poll style behavior for wait=1.
        if wait_for_update and timeline_id <= last_timeline_id:
            timeout_s = 9.5
            start = monotonic()
            while self.server.play_mgr.get_timeline_id() <= last_timeline_id:
                if monotonic() - start >= timeout_s:
                    self.send_resp('', web_header(self.server.config))
                    self.log.debug('No timeline change for wait poll, return empty response')
                    return
                sleep(0.25)

        timeline_id = self.server.play_mgr.get_timeline_id()
        changed = timeline_id > last_timeline_id
        msg = sub_mgr.msg().format(command_id=request_params.get('commandID', 0))

        if changed or (sub_mgr.is_playing and not wait_for_update):
            self.send_resp(msg, web_header(self.server.config))
            self.server.timeline_tracker[client_uuid] = timeline_id
            self.log.debug('Send current state to Plex web clients')
        elif not sub_mgr.stop_send_to_web:
            sub_mgr.stop_send_to_web = True
            self.send_resp(msg, web_header(self.server.config))
            self.server.timeline_tracker[client_uuid] = timeline_id
            self.log.info('Signal stop to Plex web clients once')
        else:
            self.send_resp('', web_header(self.server.config))
            self.log.debug('No timeline change, return empty response')


class HTTPServer(ThreadingHTTPServer):
    def __init__(self, config, sub_mgr, play_mgr):
        self.sub_mgr = sub_mgr
        self.play_mgr = play_mgr
        self.config = config
        self.client_dict = {}
        self.timeline_tracker = {}
        self.stopped = Event()
        ThreadingHTTPServer.__init__(self, ('0.0.0.0', config.companion_port), RequestHandler)
        self.server_thread = Thread(target=self.serve_forever, args=(0.5,), daemon=True)
        self.server_thread.start()

    def stop(self):
        self.shutdown()
        self.server_thread.join()
        self.socket.close()
