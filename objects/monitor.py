# -*- coding: utf-8 -*-

#################################################################################################

import binascii
import json
import logging

import xbmc

import database
from hooks import monitor
from helper import window, settings, playutils
from objects.play import playlist

#################################################################################################

LOG = logging.getLogger("EMBY."+__name__)

#################################################################################################


class Monitor(monitor.Monitor):


    def __init__(self):
        monitor.Monitor.__init__(self)

    def onNotification(self, sender, method, data):

        if sender.lower() not in ('plugin.video.emby', 'xbmc', 'upnextprovider.signal'):
            return

        if sender == 'plugin.video.emby':
            method = method.split('.')[1]

            if method not in self.get_plugin_video_emby_method():
                return

            data = json.loads(data)[0]

        elif sender.startswith('upnextprovider'):
            method = method.split('.')[1]

            if method not in ('plugin.video.emby_play_action'):
                return

            method = "Play"
            data = json.loads(data)
            data = json.loads(binascii.unhexlify(data[0])) if data else data
        else:
            if method not in self.get_xbmc_method():

                LOG.info("[ %s/%s ]", sender, method)
                LOG.debug(data)

                return

            data = json.loads(data)

        return self.on_notification(sender, method, data)

    def ReportProgressRequested(self, server, data, *args, **kwargs):
        self.player.report_playback(data.get('Report', True))

    def Play(self, server, data, *args, **kwargs):
        playlist.Playlist(data.get('ServerId'), data['ItemIds'], playlist.PLAY.get(data['PlayCommand']),
                          data.get('StartPositionTicks', 0), data.get('MediaSourceId'), data.get('AudioStreamIndex'),
                          data.get('SubtitleStreamIndex'), data.get('StartIndex'))

    def Player_OnPlay(self, server, data, *args, **kwargs):
        
        ''' Setup progress for emby playback.
        '''
        player = xbmc.Player()

        try:
            kodi_id = None

            if player.isPlayingVideo():

                ''' Seems to misbehave when playback is not terminated prior to playing new content.
                    The kodi id remains that of the previous title. Maybe onPlay happens before
                    this information is updated. Added a failsafe further below.
                '''
                item = player.getVideoInfoTag()
                kodi_id = item.getDbId()
                media = item.getMediaType()

            if kodi_id is None or int(kodi_id) == -1 or 'item' in data and 'id' in data['item'] and data['item']['id'] != kodi_id:

                item = data['item']
                kodi_id = item['id']
                media = item['type']

            LOG.info(" [ play ] kodi_id: %s media: %s", kodi_id, media)

        except (KeyError, TypeError):
            LOG.debug("Invalid playstate update")

            return

        if settings('useDirectPaths') == '1' or media == 'song':
            item = database.get_item(kodi_id, media)

            if item:

                try:
                    file = player.getPlayingFile()
                except Exception as error:
                    LOG.error(error)

                    return

                item = server['api'].get_item(item[0])
                item['PlaybackInfo'] = {'Path': file}
                playutils.set_properties(item, 'DirectStream' if settings('useDirectPaths') == '0' else 'DirectPlay')

    def VideoLibrary_OnUpdate(self, server, data, *args, **kwargs):

        ''' Only for manually marking as watched/unwatched
        '''
        try:
            kodi_id = data['item']['id']
            media = data['item']['type']
            playcount = int(data['playcount'])
            LOG.info(" [ update/%s ] kodi_id: %s media: %s", playcount, kodi_id, media)
        except (KeyError, TypeError):
            LOG.debug("Invalid playstate update")

            return

        item = database.get_item(kodi_id, media)

        if item:

            if not window('emby.skip.%s.bool' % item[0]):
                server['api'].item_played(item[0], playcount)

            window('emby.skip.%s' % item[0], clear=True)

    def Playlist_OnClear(self, server, data, *args, **kwargs):

        ''' Safe to replace in child class.
        '''
        LOG.info("[ reset autoplay ]")
        window('emby.autoplay', clear=True)
        self.player.played = {}

    def Playlist_OnAdd(self, server, data, *args, **kwargs):

        ''' Detect widget playback. Widget for some reason, use audio playlists.
        '''
        self.playlistid = data['playlistid']

        LOG.info(data)
        if window('emby.playlist.start') and data['position'] == int(window('emby.playlist.start')):

            LOG.info("--[ playlist ready ]")
            window('emby.playlist.ready.bool', True)
            window('emby.playlist.start', clear=True)
