# PlexMusicBridge (experimental)
This project aims to bridge the gap between Plex and HiFi music players like the Cambridge Azur 851N. 
The software allows to use a UPnP capable player as a Plex casting target with support for most control commands 
(play, pause, seek, volume, ...). **Please note that this is only intended to be used with music for now. The software
is provided as is without any support, warranty or guarantee that it works for you.**

### Supported Players
Feel free to add a player via PR! You can use `player/template.py` as a starting point to implement all necessary 
functionalities for your player.

 - VLC via Python API (install Python package `python-vlc`)
 - Cambridge Azur 851N

### Installation
Download the source code:
```
git clone https://github.com/niclasku/plexmusicbridge
```

Install dependencies:
```
pip3 install plexmusicbridge/
```

### Usage
You can either use command line arguments or environment variables for configuration. Example for Azur 851N:
```
plexmusicbridge -p 851n --log_level error --player_ip 192.168.10.8 --player_host_ip 192.168.10.9
```

To show all command line options, run (each player can add its own arguments that might not show up here):
```
plexmusicbridge --help
```

### Docker
You can also run this software as a Docker container. 
Following environment variables are present by default:

| ENV                     | Description                                                                 | Required | Default        |
| ----------------------- | ----------------------------------------------------------------------------|----------|----------------|
| PLAYER_NAME             | Name of player implementation (e.g. `vlc` or `851n`)                        | Yes      |                |
| LOG_PATH                | Path to log files inside the container                                      |          | ./             |
| LOG_LEVEL               | Log level (`error`, `warning`, `info` or `debug`)                           |          | error          |
| GDM_PORT                | Port for Plex GDM requests                                                  |          | 32412          |
| COMPANION_PORT          | Port of Plex Companion request handler                                      |          | 32005          |
| TITLE                   | Player name, shows up on all Plex apps                                      |          | Player         |
| SUBTITLE                | Player subtitle, shows up on Plex web clients below the player name         |          | Music Bridge   |
| NOTIFY_INTERVAL         | Interval to send current playback state to all clients and Plex server      |          | 0.5            |
| GDM_INTERVAL            | Interval to announce the player to Plex clients and server                  |          | 0.5            |

For Azur 851N:

| ENV                     | Description                                                                 | Required | Default        |
| ----------------------- | ----------------------------------------------------------------------------|----------|----------------|
| PLAYER_IP               | IP address of Azur 851N                                                     | Yes      |                |
| PLAYER_PORT             | Port for UPnP endpoint of player                                            |          | 8050           |
| HOST_IP                 | IP address of host system                                                   | Yes      |                |
| NOTIFY_PORT             | Port of UPnP message handler                                                |          | 30111          |

### Notes
- check if all *.plex.direct domains resolve on host system

### Credits
- The Plex companion implementation was adapted from @Hippojay (see https://github.com/hippojay/script.plexbmc.helper/) 
  and @croneter (see https://github.com/croneter/PlexKodiConnect/)
- The Azur 851N UPnP implementation was adapted from @cherezov (see https://github.com/cherezov/dlnap)

### ToDo
- [ ] use JSON instead of XML for communication with Plex clients and server
- [ ] add code documentation
- [ ] fix a bug where the web client looses its connection if 851N is used as player
- [ ] automatic configuration
- [ ] improve code style (e.g. private methods)
- [ ] add tests
- [ ] replace polling in 851N implementation
- [ ] container should allow port forwarding not just host network
