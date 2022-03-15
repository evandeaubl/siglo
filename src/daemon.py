import gatt

import gi.repository.GLib as glib
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from .bluetooth import InfiniTimeManager, InfiniTimeDevice, NoAdapterFound
from .config import config


class daemon:
    def __init__(self):
        self.conf = config()
        self.manager = InfiniTimeManager()
        self.device = InfiniTimeDevice(manager=self.manager, mac_address=self.conf.get_property("last_paired_device"), thread=False)
        self.mainloop = glib.MainLoop()

    def start(self):
        DBusGMainLoop(set_as_default=True)
        self.device.connect()
        self.scan_for_notifications()
        self.scan_for_music()
        self.mainloop.run()

    def stop(self):
        self.mainloop.quit()
        self.device.disconnect()

    def scan_for_notifications(self):
        monitor_bus = dbus.SessionBus(private=True)
        try:
            dbus_monitor_iface = dbus.Interface(monitor_bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus'), dbus_interface='org.freedesktop.DBus.Monitoring')
            dbus_monitor_iface.BecomeMonitor(["interface='org.freedesktop.Notifications', member='Notify'"], 0)
        except dbus.exceptions.DBusException as e:
            print(e)
            return
        monitor_bus.add_message_filter(self.notifications)

    def scan_for_music(self):
        bus = dbus.SessionBus()
        try:
            bus.add_signal_receiver(self.music_update,
                path='/org/mpris/MediaPlayer2',
                dbus_interface='org.freedesktop.DBus.Properties',
                signal_name='PropertiesChanged',
                sender_keyword='sender'
            )
        except dbus.exceptions.DBusException as e:
            print(e)
            return

    def notifications(self, bus, message):
        alert_dict = {}
        for arg in message.get_args_list():
            if isinstance(arg, dbus.Dictionary):
                if arg["desktop-entry"] == "sm.puri.Chatty":
                    alert_dict["category"] = "SMS"
                    alert_dict["sender"] = message.get_args_list()[3]
                    alert_dict["message"] = message.get_args_list()[4]
        alert_dict_empty = not alert_dict
        if len(alert_dict) > 0:
            print(alert_dict)
            self.device.send_notification(alert_dict)

    def music_update(self, interface_name, params, unknown, **kwargs):
        sender = kwargs.get('sender', None)
        music_update = {}
        if 'Metadata' in params:
            if 'xesam:artist' in params['Metadata']:
                music_update['artist'] = str(params['Metadata']['xesam:artist'][0])
            if 'xesam:title' in params['Metadata']:
                music_update['track'] = str(params['Metadata']['xesam:title'])
            if 'xesam:album' in params['Metadata']:
                music_update['album'] = str(params['Metadata']['xesam:album'])
            if 'xesam:trackNumber' in params['Metadata']:
                music_update['track_number'] = int(params['Metadata']['xesam:trackNumber'])
            if 'mpris:length' in params['Metadata']:
                music_update['length'] = int(int(params['Metadata']['mpris:length']) / 1000000)
        if 'PlaybackStatus' in params:
            if str(params['PlaybackStatus']) == 'Playing':
                music_update['playing'] = True
                # force position update to work around Infinitime bug (?)
                # FIXME doing this synchronously is probably not a good idea
                if sender is not None:
                    bus = dbus.SessionBus()
                    player = bus.get_object(sender, '/org/mpris/MediaPlayer2')
                    properties_iface = dbus.Interface(player, 'org.freedesktop.DBus.Properties')
                    music_update['position'] = int(int(properties_iface.Get('org.mpris.MediaPlayer2.Player', 'Position')) / 1000000)
            else:
                music_update['playing'] = False
        if len(music_update) > 0:
            self.device.send_music_update(music_update)
