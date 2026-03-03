import requests
import xmltodict
import socket


class PlexServer:
    def __init__(self):
        self.protocol = ''
        self.address = ''
        self.port = ''
        self.token = ''
        self.machine_id = ''

    def build_url(self, resource, token=True, rewrite_http=False, rewrite_host=None):
        if rewrite_http:
            protocol = 'http'
        else:
            protocol = self.protocol

        if rewrite_host:
            address = socket.gethostbyname(self.address)
        else:
            address = self.address

        url = protocol + '://' + address
        if self.port:
            url += ':' + str(self.port)
        if '?' in resource and token:
            url = url + resource + '&X-Plex-Token=' + self.token
        elif token:
            url = url + resource + '?X-Plex-Token=' + self.token
        else:
            url = url + resource
        return url

    def get_info(self):
        return {
            'protocol': self.protocol,
            'address': self.address,
            'port': self.port,
            'machineIdentifier': self.machine_id
        }

    def update(self, opt):
        if opt.get('protocol'):
            self.protocol = opt['protocol']
        if opt.get('address'):
            self.address = opt['address']
        if opt.get('port'):
            self.port = str(opt['port'])
        elif self.protocol and not self.port:
            self.port = '443' if self.protocol == 'https' else '80'
        if opt.get('token'):
            self.token = opt['token']
        if opt.get('machineIdentifier'):
            self.machine_id = opt['machineIdentifier']

    def get_queue(self, container_key):
        if not self.protocol or not self.address:
            raise ValueError('Missing Plex server connection data (protocol/address)')
        url = self.build_url(container_key)
        resp = requests.get(url, headers={'Accept': '*/*', 'Content-Type': 'application/json'})
        return xmltodict.parse(resp.content, 'utf-8')
