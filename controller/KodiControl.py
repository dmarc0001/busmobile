#!/usr/bin/python3
#
# Mediensteuerung fuer KODI auf RASPI


import requests
import psutil
from time import sleep, time
import re
import subprocess
import os
import logging


class KodiException(Exception):
    """
    Eine eigene Exception definieren
    """
    def __init__(self, message):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)


class KodiControl:
    """
    Klasse fuer die Kommunikation mit KODI
    """
    # headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' }
    woParamTemplate = '{"jsonrpc": "2.0", "id": "1", "method": "%s"}'
    paramTemplate = '{"jsonrpc": "2.0", "id": "1", "method": "%s", "params": %s }'
    mediaPlayerExec = '/usr/bin/kodi'
    mediaPlayerParam = '-fs'
    mediaPlayerName = 'kodi'
    rxError = re.compile(".*['\"]error['\"].*", re.IGNORECASE)
    rxPlOpen = re.compile(".*['\"]Player.Open['\"].*", re.IGNORECASE)

    def __init__(self, logger=None, url="http://localhost:8080/jsonrpc"):
        """
        Konstruktor
        :param logger: Programmlogger
        :param url: Verbindungs-URL für KODI-API
        """
        self.log = logger
        self.playerUrl = url
        self.playerStartTime = int(0)
        self.log.debug("init, url: %s..." % self.playerUrl)

    def __del__(self):
        """Destruktor"""
        self.log.debug("destructor...")

    def is_kodi_running(self):
        """
        Läuft KODI
        :return: True, wenn ja
        """
        for pid in psutil.pids():
            p = psutil.Process(pid)
            if p.name() == self.mediaPlayerName:
                self.log.debug("kodi is running...")
                return True
        self.log.debug("kodi is NOT running...")
        return False

    def app_start_kodi(self):
        """Starte KODI"""
        # laeuft nicht, ich versuch mal zu starten
        for timerVal in range(20):
            self.log.debug("kodi not running yet...Try to start (%d)" % int(timerVal))
            pid_kodi = os.spawnl(os.P_NOWAIT, self.mediaPlayerExec, self.mediaPlayerParam)
            self.log.debug("kodi starting with pid %d" % int(pid_kodi))
            sleep(5)
            if self.is_kodi_running():
                self.log.info("kodi should started...")
                return True
        return False

    def app_quit_kodi(self):
        """
        Beende KODI
        :return: Erfolgreich?
        """
        self.log.info("quit kodi...")
        cmd = self.woParamTemplate % "Application.Quit"
        self.log.debug("result from quit kommando: %s " % str(self.send_request_json(cmd)))
        sleep(2)
        if self.is_kodi_running():
            # zur Sicherheit killen, wenn quit nicht klappt
            self.log.warning("kodi is always run, try system term...")
            subprocess.run(['/usr/bin/pkill', '-SIGTERM', 'kodi'])
            self.log.warning("kodi is always run, try system term...OK")
            sleep(1.2)
        if self.is_kodi_running():
            # zur Sicherheit killen, wenn quit nicht klappt
            self.log.warning("kodi is always run, try system kill...")
            subprocess.run(['/usr/bin/pkill', '-SIGKILL', 'kodi'])
            self.log.warning("kodi is always run, try system kill...OK")
        return True

    def app_get_ping(self):
        """
        Erwarte PONG Antwort auf PING beim Kodi
        :return: Erfolgreich?
        """
        self.log.debug("getPing...")
        cmd = self.woParamTemplate % "JSONRPC.Ping"
        try:
            result = self.send_request_json(cmd)
            self.log.debug("answer for ping: %s" % str(result))
            if self.rxError.match(str(result)) is None:
                return True
            return False
        except KodiException:
            return False

    def app_get_json_version(self):
        """
        Erfrage JSON API Version vom KODI
        :return: Version oder None
        """
        self.log.debug("getJsonVersion...")
        cmd = self.woParamTemplate % "JSONRPC.Version"
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def app_set_volume(self, volume=int(50)):
        """
        Lautstärke des KODI setzten
        :param volume: Lautstärke
        :return: Antwort oder None
        """
        self.log.debug("app_set_volume...")
        params = '{ "volume": %d}' % int(volume)
        cmd = self.paramTemplate % ("Application.SetVolume", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def gui_goto_home(self):
        """HOME Screen der GUI ansteuern"""
        self.log.debug("goto homescreen...")
        cmd = self.woParamTemplate % "Input.Home"
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def gui_show_info_notification(self, title, message, timeout):
        """
        Show Info in GUI
        :param title: Titel der Nachricht
        :param message: Nachricht selbst
        :param timeout: Anzeigedauer in Sekunden
        :return: Antwort von KODI
        """
        return self.gui_show_notification(title, message, timeout, "info")

    def gui_show_warn_notification(self, title, message, timeout):
        """
        Show Warnung in der GUI
        :param title: Titel der Warnung
        :param message: die Warnung selbst
        :param timeout: Anzeigedauer in Sekunden
        :return: Antwort vom KODI
        """
        return self.gui_show_notification(title, message, timeout, "warning")

    def gui_show_err_notification(self, title, message, timeout):
        """
        Show Fehlermeldung in der GUI
        :param title: Titel der Fehlermeldung
        :param message: Fehlermeldung
        :param timeout: Anzeigedauer
        :return: Antwort von KODI
        """
        return self.gui_show_notification(title, message, timeout, "error")

    def gui_show_notification(self, title, message, timeout, m_type):
        """
        Zeige eine Nachricht vom Typ m_type in der GUI an
        :param title: Titel der Nachricht
        :param message: die Nachricht selber
        :param timeout: Anzeigedauer
        :param m_type: Typt der Nachricht
        :return: Antwort vom KODI oder None
        """
        self.log.debug("show notification %s..." % m_type)
        params = '{ "title": "%s", "message": "%s", "image": "%s", "displaytime": %d }' \
            % (title, message, m_type, timeout)
        cmd = self.paramTemplate % ("GUI.ShowNotification", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def player_get_players(self, which="all"):
        """
        Welche Player vom Typ wich gibt es
        :param which: Typ der Player, die abgefragt werden sollen
        :return: Playerliste oder None
        """
        self.log.debug("get %s Players..." % which)
        params = '{ "media": "%s" }' % which
        cmd = self.paramTemplate % ("Player.GetPlayers", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def player_get_playing(self):
        """
        Welche Player spielen Medien ab?
        :return:
        """
        self.log.debug("get Playing...")
        cmd = self.woParamTemplate % "Player.GetActivePlayers"
        ret_val = self.send_request_json(cmd)
        if isinstance(ret_val, list):
            return ret_val
        return None

    def player_get_play_time(self):
        """
        Erfrage die Spielzeit eines aktiven Players
        :return: Speilzeit in Sekunden
        """
        self.log.debug("get play time...")
        return int(time()) - self.playerStartTime

    def player_is_play_time_over(self, duration):
        """
        Ist die Spielzeit duration schon vorbei?
        :param duration: avisierte Spielzeit
        :return: ist die Zeit um?
        """
        self.log.debug("play time is over?")
        if int(self.playerStartTime + duration) < int(time()):
            return True
        return False

    def player_ppen_playlist(self, playlistid):
        """
        Öffne eine Playlist mit ID
        :param playlistid: welche Playlist öffnen?
        :return: Erfolgreich oder None
        """
        self.playerStartTime = int(time())
        self.log.debug("open Playlist %d..." % int(playlistid))
        params = '{ "item": { "playlistid": %s, "position": 0 } }' % int(playlistid)
        cmd = self.paramTemplate % ("Player.Open", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def player_open_file(self, file_name):
        """
        öffne Mediendatei zum abspielen
        :param file_name: dateiname der Mediendatei
        :return: Antwort von KODI oder None
        """
        self.playerStartTime = int(time())
        self.log.debug("open File %s..." % file_name)
        params = '{ "item": { "file": "%s" } }' % file_name
        cmd = self.paramTemplate % ("Player.Open", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def player_stop(self, playerid):
        """
        Stoppe Player mit playerid
        :param playerid: is des Players zum stoppen
        :return: Antwort von KODI oder None
        """
        self.playerStartTime = 0
        self.log.debug("play stop...")
        params = '{ "playerid": %s }' % playerid
        cmd = self.paramTemplate % ("Player.Stop", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def player_all_stop(self):
        """
        Stoppe ALLE Player
        :return: Erfolgreich?
        """
        self.log.debug("play all stop...")
        # welche sind aktiv
        player_arr = self.player_get_playing()
        if player_arr is None:
            return True
        for player in player_arr:
            params = '{ "playerid": %s }' % player["playerid"]
            cmd = self.paramTemplate % ("Player.Stop", params)
            self.send_request_json(cmd)
        self.playerStartTime = 0
        return True

    def player_pause_toggle(self, playerid):
        """
        wechsle den Pausezustand des Players playerid
        :param playerid: id des Players
        :return: erfolg oder None
        """
        self.log.debug("play Pause toggle...")
        params = '{ "playerid": %s, "play": "toggle" }' % playerid
        cmd = self.paramTemplate % ("Player.PlayPause", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def playlist_get_lists(self):
        """
        gib alle Playlists zurück
        :return:
        """
        self.log.debug("get playlists...")
        cmd = self.woParamTemplate % "Playlist.GetPlaylists"
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def playlist_clear_list(self, listid):
        """
        Leere Playlist mit der ID listid
        :param listid: id der Liste
        :return: ERfolgreich oder None
        """
        self.log.debug("clear playlist %d..." % int(listid))
        params = '{ "playlistid": %d }' % listid
        cmd = self.paramTemplate % ("Playlist.Clear", params)
        result = self.send_request_json(cmd)
        if self.rxError.match(str(result)) is None:
            return result
        return None

    def playlist_clear_all(self):
        """
        Leere alle Playlists
        :return: Erfolgreich oder None
        """
        self.log.debug("clear all playlists...")
        lists = self.playlist_get_lists()
        if lists is None:
            return False
        for play_list in lists:
            self.playlist_clear_list(play_list["playlistid"])
        return True

    def playlist_get_video_list(self):
        """
        Gib die Video Playlist zurück
        :return: Liste oder None
        """
        self.log.debug("get video playlists...")
        lists = self.playlist_get_lists()
        if lists is None:
            return None
        for play_list in lists:
            if play_list["type"].startswith("video"):
                self.log.debug("video playlists: %d" % int(play_list["playlistid"]))
                return int(play_list["playlistid"])
        return None

    def playlist_get_picture_list(self):
        """
        Gib die Biler Playliste zurück
        :return: Liste oder None
        """
        self.log.debug("get picture playlists...")
        lists = self.playlist_get_lists()
        if None is lists:
            return None
        for play_list in lists:
            if play_list["type"].startswith("picture"):
                self.log.debug("picture playlists: %d" % int(play_list["playlistid"]))
                return int(play_list["playlistid"])
        return None

    def playlist_add_item(self, listid, item):
        """
        füge der Liste litsid einen eintrag item hinzu
        :param listid: Liste zum zufügen
        :param item: Eintag
        :return: Erfolg oder None
        """
        self.log.debug("add item to playlist %d..." % int(listid))
        params = '{ "item": { "file": "%s" }, "playlistid": %d }' % (item, listid)
        cmd = self.paramTemplate % ("Playlist.Add", params)
        result = self.send_request_json(cmd)
        if None is self.rxError.match(str(result)):
            return result
        return None

    def send_request_json(self, params):
        """
        Sende eine JSON codierte Nachricht/Kommando an KODI
        :param params: Die Nachricht als JSON String
        :return: Erfolg oder ERROR
        """
        self.log.debug("start get json request...")
        my_data = {'request': params}
        self.log.debug("send params to kodi: %s" % str(params))
        try:
            r = requests.get(self.playerUrl, params=my_data, timeout=(3, 5))
            resp = r.json()
            self.log.debug("send params to kodi: OK")
        except ConnectionRefusedError:
            self.log.error("connection error")
            return {"error": "connection error"}
        except requests.exceptions.ReadTimeout as msg:
            self.log.error("timeout while GET %s" % str(msg))
            if None is self.rxError.match(str(msg)):                
                # TODO: workarround, bei der RASPI Version haengt der aufruf
                return "OK"
            return {"error": "timeout while GET %s" % str(msg)}
        except Exception as msg:
            self.log.error("unexpected error")
            return {"error": "unexcepcted error %s" % str(msg)}
        try:
            ret_val = resp["result"]
            self.log.debug("request result: %s" % str(ret_val))
            return ret_val
        except Exception:
            self.log.warning("cant't find result from response. try error...")
            try:
                ret_val = resp["error"]
                self.log.error('request error: \"%s\"' % ret_val)
                return ret_val
            except Exception:
                return {"error": "not an valid response from kodi"}
