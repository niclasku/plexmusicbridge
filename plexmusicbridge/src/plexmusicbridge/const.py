# GDM constants
GDM_MULTICAST_ADDR = '239.0.0.250'
GDM_MULTICAST_PORT = 32413
GDM_HEADER = '* HTTP/1.0'
GDM_DATA = 'Content-Type: plex/media-player\nResource-Identifier: {}\nName: {}\nPort: {}\nProduct: {}\nVersion: {' \
           '}\nProtocol: plex\nProtocol-Version: 1\nProtocol-Capabilities: timeline,playback,' \
           'playqueues\nDevice-Class: STB\n '

# Listener constants
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'
XML_OK = XML_HEADER + '<Response code="200" status="OK"/>'
XML_RES = '<MediaContainer>\n<Player title="{}" protocol="plex" protocolVersion="1" ' \
          'protocolCapabilities="timeline,playback,playqueues" machineIdentifier="{}" product="{}" platform="{}" ' \
          'platformVersion="{}" version="{}" deviceClass="stb"/>\n</MediaContainer>\n '

# Timeline XML notifications
TIMELINE_STOPPED = '<MediaContainer commandID="{command_id}">' \
                   '<Timeline type="music" state="stopped"/>' \
                   '<Timeline type="video" state="stopped"/>' \
                   '<Timeline type="photo" state="stopped"/>' \
                   '</MediaContainer>'

CONTROLLABLE = 'playPause,stop,volume,shuffle,repeat,seekTo,skipPrevious,skipNext,stepBack,stepForward'

TIMELINE_PLAYING = '<MediaContainer commandID="{command_id}"><Timeline controllable="' + CONTROLLABLE + '" ' \
                   'type="music" {parameters}/><Timeline type="video" state="stopped"/><Timeline type="photo" ' \
                   'state="stopped"/></MediaContainer> '


def web_header(config):
    return {
        'X-Plex-Client-Identifier': config.client_id,
        'X-Plex-Protocol': '1.0',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Max-Age': '1209600',
        'Access-Control-Expose-Headers': 'X-Plex-Client-Identifier',
        'Content-Type': 'text/xml;charset=utf-8'
    }


def resource_xml(config):
    return (XML_HEADER + XML_RES).format(config.title, config.client_id, config.product, config.platform,
                                         config.platform_version, config.version)


def device_header(config):
    return {
        'Accept': '*/*',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept-Language': 'en',
        'X-Plex-Device': config.product,
        'X-Plex-Platform': config.platform,
        'X-Plex-Platform-Version': config.platform_version,
        'X-Plex-Product': config.title,
        'X-Plex-Version': config.version,
        'X-Plex-Client-Identifier': config.client_id,
        'X-Plex-Provides': 'client,player,pubsub-player',
    }


def pms_header(config):
    return {
        'X-Plex-Client-Identifier': config.client_id,
        'X-Plex-Device': config.product,
        'X-Plex-Device-Name': config.product,
        'X-Plex-Platform': config.platform,
        'X-Plex-Platform-Version': config.platform_version,
        'X-Plex-Product': config.title,
        'X-Plex-Version': config.version,
    }


def companion_header(config):
    return {
        'Content-Type': 'application/xml',
        'Connection': 'Keep-Alive',
        'X-Plex-Client-Identifier': config.client_id,
        'X-Plex-Device-Name': config.product,
        'X-Plex-Platform': config.platform,
        'X-Plex-Platform-Version': config.platform_version,
        'X-Plex-Product': config.title,
        'X-Plex-Version': config.version,
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en,*'
    }
