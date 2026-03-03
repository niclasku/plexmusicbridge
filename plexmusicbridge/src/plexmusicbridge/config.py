class Config:
    def __init__(self, player_name, player, log_path=None, gdm_port=None, companion_port=None, title=None, product=None,
                 notify_interval=None, gdm_interval=None):
        self.player = player
        self.gdm_port = gdm_port or 32412
        self.companion_port = companion_port or 32005
        self.title = title or 'Player'
        self.product = product or 'Music Bridge'
        self.version = '4.12.4'
        self.client_id = '60982fb8-6b50-4abf-8efe-3de684627661'
        self.platform = 'Linux'
        self.platform_version = '0.1'
        self.player_name = player_name or 'vlc'
        self.log_path = log_path or './'
        self.notify_interval = notify_interval or 0.5
        self.gdm_interval = gdm_interval or 0.5
