import requests
import xmltodict


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
            address = rewrite_host
        else:
            address = self.address

        url = protocol + '://' + address + ':' + self.port
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
        if {'protocol', 'address', 'port', 'token', 'machineIdentifier'}.issubset(opt.keys()):
            self.protocol = opt['protocol']
            self.address = opt['address']
            self.port = opt['port']
            self.token = opt['token']
            self.machine_id = opt['machineIdentifier']

    def get_queue(self, container_key):
        url = self.build_url(container_key)
        resp = requests.get(url, headers={'Accept': '*/*', 'Content-Type': 'application/json'})
        return xmltodict.parse(resp.content, 'utf-8')
