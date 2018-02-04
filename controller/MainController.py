#!/usr/bin/python3
# coding=utf-8
#

from time import time, sleep
import logging
import socket
from KodiControl import KodiException, KodiControl
from MediaControl import *
from GeoLocThread import GeoLocationThread
from ControlXmlParser import ControlXmlParser

"""
KODI Mediaplayer mit GPS Hauptprogramm
"""
__author__    = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__   = 'GPL'
__version__   = '0.1'

# TODO: Betrtiebsart POI oder durchlaufend

"""
    Das Hauptprogramm als Objekt
"""


class MainObject:
    """
    Das Hauptobjekt, kapselt alle anderen objekte rund um das Progamm
    """
    DEFAULT_PICTURE_DURATION = int(20)

    """
    Der Konstruktor

    Args:
        logger: der fertige Logger 
        kControl: das Objekt für die Kontrolle/Steuerung des Kodi
        mControl: das Objekt für das handling der Mediendateien
        playerUrl: die URL zur Steuerung des Kodi
        mSocket: Unix Socket file für IPC mit dem Displayprogramm (kleines Display)
        fileMame: die XML Datei mit Datein über die Points of interest 

    Returns:
        None
        
    Raises:
        None
    """  
    def __init__(self, logger, kodi_ontrol, media_control, player_url, display_socket, xml_filename):
        """
        Der Konstruktor
        :param logger: Das Loggerobjekt
        :param kodi_ontrol: Kodi Kontrollobjekt
        :param media_control: Media-Kontrollobjekt
        :param player_url: KODI URL für JSON API
        :param display_socket: Socket zur Kommunikation mit dem Display
        :param xml_filename:  XML Steuerdatei
        """
        self.log = logger
        # Objekte zur Kontrolle von Kodi und den Medien
        self.kodiControl = kodi_ontrol
        self.mediaControl = media_control
        self.kodiPictureDuration = MainObject.DEFAULT_PICTURE_DURATION
        self.gpsThread = GeoLocationThread(self.log)       # Threadobjekt zur Standortüberwachung
        #
        self.playerUrl = player_url                        # URL zur Steuerung des KODI
        self.unixSocketFile = display_socket               # Socket zur Kommunikation mit der kleinen Amzeige
        self.cSock = None                                  # Socketobjekt "socket"
        self.poi = None                                    # aktueller POI in dessen Umkreis ich bin
        self.controlFile = xml_filename                    # Steuerdatei
        pois = self.read_control_file(xml_filename)        # Point of interests array aus XML File
        self.isRunning = True                              # solange TRUE läuft das Programm
        self.isLocationPlay = False                        # bei True läuft die Anzeige für einen poi
        self.cSockIsConnected = False                      # Verbindung zum Display?
        self.lastConnectTime = 0                           # wann war die lettze Verbindung zum Display
        self.gpsThread.set_pois(pois)                      # übergebe die gesuchten Standortangaben an den thread
        self.connect_socket(self.unixSocketFile)           # Verbinde zum Display
        #
        # Callbacks für den Thread, damit dieser Benachrichtigungen schicken kann
        #
        self.log.debug("set callbacks to geolocation thread...")
        self.gpsThread.set_on_gps_lock(self.gps_lock_callback)
        self.gpsThread.set_on_poi_hit(self.gps_hit_callback)
        # Thread starten
        self.log.debug("start geolocation thread...")
        self.gpsThread.start() 
        
    def __del__(self):
        """Destruktor"""
        self.log.debug("destructor...")
        self.__stop_gps_thread()
        # Display leerren
        self.log.info("clear display...")
        if self.cSockIsConnected:
            try:
                msg = "undef"
                self.cSock.send(msg.encode('utf-8'))
                msg = "clear"
                self.cSock.send(msg.encode('utf-8'))
                msg = "title:SHOWSTATUS"
                self.cSock.send(msg.encode('utf-8'))
                msg = "info:Show wurde beendet"
                self.cSock.send(msg.encode('utf-8'))
                self.cSock.close()            
            except OSError:
                pass
        self.log.debug("destructor...OK")

    def __stop_gps_thread(self):
        """
        Stoppe den GPS Thread

        :return: Erfolgreich == True sonst False
        """
        if self.gpsThread is not None:
            try:
                # stoppe den gps thread
                self.log.info("stop gpsthread...")
                # callbacks löschen
                self.gpsThread.clear_on_gps_lock()
                self.gpsThread.clear_on_poi_hit()
                self.gpsThread.quit_thread()
                for stop_times in range(10):
                    self.log.debug("wait for stopping geothread {}...".format(stop_times))
                    self.gpsThread.join(1.5)
                    if self.gpsThread.is_alive():
                        break
                if not self.gpsThread.is_alive():
                    del self.gpsThread
                    self.gpsThread = None
                    self.log.debug("stop gpsthread...OK")
                    return True
                # hier ist was faul
                self.log.error("stop gpsthread...FAILED!")
                self.gpsThread = None
                return False
            except:
                self.log.fatal("error while stoppig geo thread!")
                return False
        self.log.debug("stop gpsthread: no gps thread instantiated!")
        return True

    def read_control_file(self, ctrl_file=None):
        """
        liest aus der XML Datei die POI Infos aus
        :param ctrl_file: XML Steuerdatei oder None
        :return: points of interest
        """
        # ist eine Datei erwähnt?
        if ctrl_file is not None:
            # dann die neue Datei nehmen
            self.controlFile = ctrl_file
            self.log.debug("set new xml file <%s>..." % self.controlFile)
        # parse die Datei (da sind die Steierdaten für POI drin)
        parser = ControlXmlParser(self.log, self.controlFile)
        self.log.debug("parse xml file <%s>..." % self.controlFile)
        pois = parser.parse_control_file()
        del parser
        self.log.debug("parse xml file ...OK")
        return pois
 
    def kodi_init(self):
        """
        Initialisiere den KODI
        :return: Erfolg oder None
        """
        #
        # so nun ans eingemachte
        #
        self.kodiControl.gui_goto_home()
        self.kodiControl.app_set_volume(30)
        self.kodiControl.player_all_stop()
        self.log.debug("playlists on KODI available: %s" % self.kodiControl.playlist_get_lists())
        # erst mal alle Listen loeschen
        self.kodiControl.playlist_clear_all()

    def is_media_playing(self, is_picture, play_end_time):
        """
        wird das medium noch gespielt?
        Abhängig ob Bild (vorgabezeit) oder Video (speilzeit)
        :param is_picture:  ist Medium ein Bild?
        :param play_end_time: Endezeit (für Bild)
        :return: noch in der Spielzeit?
        """
        play_in_progress = False
        players_array = self.kodiControl.player_get_playing()
        if players_array is None:
            # da spielt nichts
            return play_in_progress
        # gibt es da was?
        if isinstance(players_array, list):
            for player in players_array:
                self.log.debug("an player ist working... (%s, type: %s)"
                               % (player["playerid"], player["type"]))
                play_in_progress = True
        if play_in_progress:
            if is_picture:
                # ein Bild wird gespielt
                # Zeit abgeleufen?
                if play_end_time > time():
                    # das war es
                    return False
        return play_in_progress

    def app_running_condition(self):
        """
        Alle Bedingungen für das Programm noch aktuell?
        :return: Aktuell?
        """
        # ist die Markerdatei vorhanden?
        if self.mediaControl.check_file_exist(self.controlFile):
            return self.isRunning
        # Markerdatei fehlt, Abbruch ist da...
        self.log.info("marker file is gone (stick disappeared?). End Programm...")
        self.isRunning = False
        return self.isRunning

    def play_poi(self, mpoi):
        """
        Spiele Medium/Medien innerhalb eines Bereiches der als
        Point o interest gekennzeichnet ist
        :param mpoi: Liste mit zu spielenden Medien
        :return: True == ohne Probleme
        """
        self.log.info("play one medium/media for poi (%s)..." % mpoi['title'])
        # spiele dazwischen was vom poi
        if mpoi['medium'] is not None and len(mpoi['medium']) > 0:
            self.kodiControl.gui_show_info_notification("POI", mpoi['title'], int(15000))
            # Ok es gibt Medien
            # Liste oder einzeln?
            if len(mpoi['medium']) == 1:
                # Ein Medium...
                media_file = mpoi['medium'][0]
                self.kodiControl.player_all_stop()
                self.log.debug("play_poi: play one medium  on poi (%s)..." % media_file)
                self.log.info("play medium %s for poi (%s)..." % (media_file, mpoi['title']))
                # Kodi das Medium spielen lassen
                ret_val = self.kodiControl.player_open_file("%s/%s"
                                                            % (self.mediaControl.get_poi_media_dir(), media_file))
                if ret_val is None:
                    # das klappt nicht
                    self.log.fatal("can't play medium, abort")
                    return False
                #
                # spiele das Medium solange bis Abbrchbedingung erfüllt is
                # also bie poi None wird oder die App endet
                #
                while self.poi is not None and self.app_running_condition():
                    sleep(0.5)
                return True
            else:
                # mehrere Medien
                media_list = mpoi['medium']
                # die Liste immer wieder solange bis Ende programm oder poi is None
                while self.poi is not None and self.app_running_condition():
                    for media_file in media_list:
                        self.log.info("play medium %s for poi (%s)..." % (media_file, mpoi['title']))
                        type_of_medium = self.mediaControl.class_of_media(media_file)
                        is_picture = type_of_medium.startswith("picture")
                        play_end_time = time() + self.kodiPictureDuration
                        self.kodiControl.player_all_stop()
                        self.log.debug("play_poi: play next medium in an list on poi (%s)..." % media_file)
                        # Kodi das Medium spielen lassen
                        ret_val = self.kodiControl.player_open_file("%s/%s"
                                                                    % (self.mediaControl.get_poi_media_dir(), media_file))
                        if ret_val is None:
                            # das klappt nicht
                            self.log.fatal("can't play medium, abort")
                            return False
                        while self.app_running_condition() and self.poi is not None:
                            # resourcen schonen...
                            sleep(0.4)
                            # wiel lange spielen?
                            if self.is_media_playing(is_picture, play_end_time):
                                # das Medium spielt noch, nächste Runde warten
                                continue
                            else:
                                # Ende Medium, nächstes Medium, brich diesess while ab, weiter in for-schleife
                                break
                # Ende ELSE Zweig
                return True
            # ende if mpoi['medium'].count('medium') == 1:
        else:
            self.log.warn("no medium/media for play found....")
            return False
        #

    def main_loop(self):
        """
        Hauptschleife, läuft bis zum Programmende
        :return: None
        """
        self.log.debug("play media until the end...")
        # initialisieren
        self.kodi_init()
        self.log.debug("enter main loop..")
        # ist die Controldatei vorhanden (der Stick gesteckt)?
        if not self.app_running_condition():
            self.log.fatal("controlfile %s not found, show errormsg, abort..." % self.controlFile)
            self.kodiControl.gui_show_err_notification("FEHLER", "keine Steuerdatei gefunden...", int(15000))
            return            
        # self.kodiControl.gui_show_info_notification("START", "Beginne show...", int(8000))
        #
        # ich mache das solange, bis das System aus geht oder die Markerdatei gelöscht wird
        #
        while self.app_running_condition():
            #
            # Alle Dateien durch
            #
            for media_file in self.mediaControl.get_media_list():
                if not self.app_running_condition():
                    # Programm abbrechen
                    break
                #
                # ist ein spezielles Ereignis für einen point of interest entstanden?
                #
                if self.poi is not None:
                    self.play_poi(self.poi)
                #
                # das nächste Medium abspielen, was ist es für ein medium?
                #
                type_of_medium = self.mediaControl.class_of_media(media_file)
                is_picture = type_of_medium.startswith("picture")
                # Endezeit für Bilder
                play_end_time = time() + self.kodiPictureDuration
                self.kodiControl.player_all_stop()
                self.log.debug("play one medium  (%s)..." % media_file)
                # Kodi das Medium spielen lassen
                ret_val = self.kodiControl.player_open_file("%s/%s"
                                                            % (self.mediaControl.get_media_dir(), media_file))
                #
                # Den Rückgabewert checken
                #
                if ret_val is None:
                    # das klappt nicht
                    self.log.fatal("can't play medium, abort")
                    # ist die Kontrolldatei noch im Pfad? Alles nocham laufen?
                    if self.app_running_condition():
                        # nächstes Medium...
                        continue
                    # ENDE Gelände, Programm soll enden
                    self.log.fatal("abort program")
                    return
                # Normal weitermachen
                self.log.debug("medium should playing (retval %s)..." % str(ret_val))
                # nun warten, bis das Medium fertig ist oder ein Ereignis auftritt
                while self.app_running_condition():
                    # ist da inzwischen ein spezielles ereignis für einen poi da?
                    if self.poi is not None:
                        # da ist was, nächstes Medium est danach
                        self.play_poi(self.poi)
                        break
                    # etwas Ruhe bitte... (Resourcen sind wertvoll)
                    sleep(0.4)
                    if self.is_media_playing(is_picture, play_end_time):
                        # das Medium spielt noch, nächste Runde warten
                        continue
                    else:
                        # Ende Medium, nächstes Medium, brich diesess while ab
                        break
                # ende while
                #
                # ist der Kodi etwa aus oder anderer fehler?
                if not self.kodiControl.app_get_ping():
                    # der Kodi ist aus/tot/beendet
                    # TODO: Kennzeichne dass KODI nicht reagiert
                    self.log.fatal("kodi not running...")
                    return
                # und nun das nächste Medium
            # ende FOR Schleife, wieder zu Bedingung while.. also alles von vorne
        # Ende while, ende Schleife
        # aufräumen
        self.log.debug("main loop end...")
        self.kodiControl.player_all_stop()
        self.kodiControl.gui_show_warn_notification("ENDE", "Show beenden...", int(15000))
        if self.cSockIsConnected:
            try:
                msg = "title:STOPP"
                self.cSock.send(msg.encode('utf-8'))
                msg = "info:warten bis Programm Ende"
                self.cSock.send(msg.encode('utf-8'))
            except:
                pass
        self.__stop_gps_thread()
        sleep(5)
        self.log.debug("mail loop call final 'self.kodiControl.app_quit_kodi()'...")
        self.kodiControl.app_quit_kodi()
        self.log.debug("mail loop call final 'self.kodiControl.app_quit_kodi()'...OK")
        sleep(3)

    def gps_lock_callback(self, is_lock):
        """
        Callback vom GPS Tread, gps lock hat scih verändert
        :param is_lock: GPS ist "locked"
        :return: ERfolgreiche Funktion?
        """
        self.log.info("gps lock is %d" % is_lock)
        # ist das Display verbunden?
        if not self.cSockIsConnected or self.cSock is None:
            # teste, ob das letzte Verbinden schon länger als 10 Sekuden her ist
            if self.lastConnectTime + 10 > time():
                # versuche zu verbinden
                if not self.connect_socket(self.unixSocketFile):
                    return False
        try:
            # Sende Nachricht an das Display
            if is_lock:
                msg = "lock"
            else:
                msg = "unlock"
            self.cSock.send(msg.encode('utf-8'))
            return True
        except OSError as msg:
            self.lastConnectTime = time()
            self.log.error("while send to taskwin %s" % msg)
            self.cSockIsConnected = False
            return False

    def gps_hit_callback(self, poi):
        """
        Callback vom GPS Thread über Treffer aus der POI Liste
        :param poi: Ein Objekt mit Infos über den POI oder None
        :return: Es konnte reagiert werden
        """
        self.log.info("gps hit location is %s" % poi)
        self.poi = poi
        #
        # ist das Display Verbunden
        #
        if not self.cSockIsConnected:
            if self.lastConnectTime + 10 > time():
                if not self.connect_socket(self.unixSocketFile):
                    self.log.warn("cant send msg to display...")
                    return False
        #
        # Verbindung besteht, sende Daten
        #
        try:
            if poi is None:
                msg = "clear"
                self.cSock.send(msg.encode('utf-8'))
                return True
            self.log.info("set display title: %s, msg: %s" % (poi["title"], poi["notice"]))
            msg = "title:" + poi["title"]
            self.cSock.send(msg.encode('utf-8'))
            msg = "info:" + poi["notice"]
            self.cSock.send(msg.encode('utf-8'))
            return True
        except OSError as msg:
            self.lastConnectTime = time()
            self.log.error("while send to taskwin %s" % msg)
            self.cSockIsConnected = False
            return False
        except:
            self.log.error("unknown error while send to taskwin")
            return False

    def quit_app(self):
        """
        Steuerung von aussen wenn die Hauptschleife beendet werden soll
        :return: None
        """
        # callbacks löschen
        self.log.info("==================================================================")
        self.log.info("======================= QUIT APP REQUESTED =======================")
        self.log.info("==================================================================")
        self.isRunning = False

    def connect_socket(self, ux_sock):
        """
        Verbinde zum UnixSocket für das Display
        TODO: Algorhytmus für neues Verbinden, wenn die Verbindng verloren geht
        :param ux_sock: Unix Socket
        :return: Erfolgreich?
        """
        self.log.debug("connect to unix socket as client...")
        # kennzeichne den letzen Versuch
        self.lastConnectTime = time()
        try:
            self.cSock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.cSock.connect(ux_sock)
            self.cSockIsConnected = True
            msg = "undef"
            self.cSock.send(msg.encode('utf-8'))
            msg = "clear"
            self.cSock.send(msg.encode('utf-8'))
            return True
        except OSError as msg:
            self.log.error("while try connect to server socket <%s>: %s" % (ux_sock, msg))
            self.cSockIsConnected = False
            self.cSock = None
            return False
