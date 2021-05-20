import socket
import threading
from logging import getLogger
from time import sleep
from .const import GDM_HEADER, GDM_DATA, GDM_MULTICAST_PORT, GDM_MULTICAST_ADDR


class PlexGdm:
    def __init__(self, config):
        self.config = config
        self.client_group = (GDM_MULTICAST_ADDR, GDM_MULTICAST_PORT)
        self.port = config.gdm_port
        self.socket = None
        self.thread = None
        self.running = False
        self.log = getLogger('PlexGdm')
        self.client_data = GDM_DATA.format(config.client_id, config.title, config.companion_port,
                                           config.product, config.version)

    def hello(self):
        return ('HELLO %s\n%s' % (GDM_HEADER, self.client_data)).encode()

    def bye(self):
        return ('BYE {}\n{}'.format(GDM_HEADER, self.client_data)).encode()

    def register(self):
        try:
            data = self.hello()
            self.log.debug('Send registration data: ' + str(data))
            self.socket.sendto(data, self.client_group)
        except Exception as e:
            self.log.error('Unable to send registration message: ' + str(e))

    def initialize(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Set socket reuse, may not work on all OSs.
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception as e:
            self.log.error(e)

        # Attempt to bind to the socket to receive and send data.
        try:
            self.socket.bind(('0.0.0.0', self.port))
        except Exception as e:
            self.log.error('Unable to bind to port: ' + str(e))
            return False

        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GDM_MULTICAST_ADDR) +
                               socket.inet_aton('0.0.0.0'))
        self.socket.setblocking(False)
        return True

    def update_loop(self):
        if not self.initialize():
            return

        # Send initial client registration
        self.register()

        # Now, listen for client discovery requests and respond.
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                self.log.debug('Received UDP packet from {} containing {}'.format(addr, data.strip()))
            except socket.error:
                pass
            else:
                if 'M-SEARCH * HTTP/1.' in data.decode() and addr[0] != '127.0.0.1':
                    self.log.info('Detected client discovery request from ' + str(addr))
                    self.log.debug('Send registration data HTTP/1.0 200 OK')
                    try:
                        self.socket.sendto(('HTTP/1.0 200 OK\n' + self.client_data).encode(), addr)
                    except Exception as e:
                        self.log.error('Unable to send client update message: ' + str(e))
            sleep(self.config.gdm_interval)

        # Stopping
        self.log.info('Update loop stopped')
        data = self.bye()
        self.log.debug('Send registration data: ' + str(data))
        try:
            self.socket.sendto(data, self.client_group)
        except Exception as e:
            self.log.error('Unable to send client update message: ' + str(e))

    def stop(self):
        if self.running:
            self.log.info('Registration shutting down')
            self.running = False
            self.thread.join()
            del self.thread
        else:
            self.log.info('Registration not running')

    def start(self):
        if not self.running:
            self.log.info('Registration starting up')
            self.running = True
            self.thread = threading.Thread(target=self.update_loop, daemon=True)
            self.thread.start()
        else:
            self.log.info('Registration already running')
