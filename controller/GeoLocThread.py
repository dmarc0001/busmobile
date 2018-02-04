#!/usr/bin/python3
# coding=utf-8
# 

from geopy.distance import vincenty
from time import sleep, time
from threading import Thread, Lock
import signal
import logging
import logging.handlers
from GpsdConnect import GPSDSocket, DataStream

__author__ = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__ = 'GPL'
__version__ = '0.1'


# TODO: falls der GPSD mal die Verbindung verliert, neu verbinden, testen??? (nach 10 Sekunden neues watch schicken?)

class GeoLocationThread(Thread):
    """
    GeoLocationThread
    Thread der die Geoposition abfragt und
    über callbacks dem Programm Nachricht gibt
    """
    DEFAULT_LOGFILE = "/var/log/mediaplayer/geolocation-thread.log"
    # Radius in Metern für das Filtern der POI
    POI_RADIUS = int(1500)
    # Radius für das Annähern an eine Haltestelle
    STOP_COMIN = int(200)
    # Radius für das entfernen von einer Haltestelle
    STOP_GETOUT = int(18)
    # Zeit in Sekunden bis das nächste mal die Orte gefiltert werden    
    TIME_TO_POIFILTER = 8
    # Eichenstrasse 33, Eschede
    HOMECOORD = {"lat": "52.731559", "lon": "10.247012"}

    def __init__(self, logger, host="127.0.0.1", port=2947):
        """
        Konstruktor
        :param logger: Sytemlogger
        :param host: Host, auf dem GPSD läuft
        :param port: Port des GPST auf dem Host
        """
        Thread.__init__(self)
        if int(logger.getEffectiveLevel()) < 20:
            self.log = logger
        else:
            self.log = self.make_logger(logging.DEBUG)
        self.log.debug("thread object instantiate...")
        # gpsd sachen
        self.gpsdHost = host
        self.gpsdPort = port
        self.gpsdSocket = GPSDSocket(self.log)
        self.gpsdDataStream = DataStream(self.log)
        # thread bezogen
        self.watchdogTime = time() + GeoLocationThread.TIME_TO_POIFILTER
        self.isGpsdConnected = False
        self.isRunning = False
        self.gpsPosition = None
        self.POI = []
        self.STOPS = []
        self.hitPoi = None
        self.hitStop = None
        self.currPois = []
        self.currStops = []
        self.callBackHitLocation = None
        self.callBackLockGPS = None
        self.lock = Lock()
        self.isGpsLock = False  # merker falls callback da ist, damit callback nicht mehrfach aufgerufen wird
        # gpsd verbinden
        self.isGpsdConnected = self.connect()
        self.log.debug("thread object instantiate...OK")

    def __del__(self):
        """Destruktor"""
        if self.log is not None:
            self.log.debug("destructor...")
        if self.isGpsdConnected:
            self.gpsdSocket.close()

    def quit_thread(self):
        """Thread beenden"""
        self.log.info("== initiate gps-thread shutdown ==")
        self.isRunning = False

    def is_thread_running(self):
        """
        sollte der Thread noch laufen?
        :return: Läuft der Thread?
        """
        return self.isRunning

    def connect(self):
        """
        Verbinde mit dem GPS Daemon
        :return: Verbindung erfolgreich?
        """
        # host='127.0.01', port=2947, gpsd_protocol='json', and usnap=0.2        
        try:
            self.log.debug("gpsd connect...")
            # Verbinden mit defaults
            self.log.debug("gpsd connection...")
            if self.gpsdSocket.connect():
                self.log.debug("gpsd connection ok, socket watch...")
                if self.gpsdSocket.watch():
                    self.log.debug("gpsd socket watch...OK")
                    return True
        except:
            self.log.error("can't gpsd connect...")
        return False

    def reconnect(self):
        """Neuverbinden mit dem GPS Daemon"""
        self.isGpsdConnected = self.connect()
        return self.isGpsdConnected

    def run(self):
        """
        Hauptschleife des Thread
        :return: None
        """
        # vorbedingng setzen
        self.isRunning = True
        #
        while self.isRunning:
            #
            # versuche die Position zu bestimmen
            # wenn ein 2d-Fix vorhanden ist
            #
            sleep(2)
            # verbunden mit gpsd?
            if not self.isGpsdConnected:
                self.log.warning("gpsd not connected...")
                # position löschen
                self.lock.acquire()
                self.gpsPosition = None
                self.lock.release()
                # ist ein Callback notwendig?
                if self.isGpsLock:
                    self.isGpsLock = False
                    self.log.info("gpsd now connected...")
                    if self.callBackLockGPS is not None:
                        self.callBackLockGPS(self.isGpsLock)
                self.reconnect()
                continue
            #
            # jetzt Daten holen
            #
            if self.isRunning:
                self.__read_data()

    def __read_data(self):
        """
        privat, lese daten vom gpsd
        die gps daten sind lock geschützt, da auch von ausserhalb zugegriffen werden kann
        daher muss gleichzeitiger zugriff verboten sein
        das ist threadsave...
        :return: None
        """
        # Alle vorhanden Daten lesen
        for gpsData in self.gpsdSocket:
            # immer die Abbruchbedingung in der sicht behalten
            if not self.isRunning:
                return
            if gpsData:
                # es gibt Daten!
                self.log.debug("get current position...")
                self.gpsdDataStream.unpack(gpsData)
                try:
                    # feststellen, ob es einen lock vom GPS gibt
                    self.log.debug("mode: %d, pos: lat: %s, lon %s" % (
                        int(self.gpsdDataStream.TPV['mode']), self.gpsdDataStream.TPV['lat'],
                        self.gpsdDataStream.TPV['lon']))
                    mode = int(self.gpsdDataStream.TPV['mode'])
                except:
                    # etwas ging schief, also auch kein lock
                    mode = -1
                    self.log.warning("gps cant read (mode)...")
                    self.lock.acquire()
                    self.gpsPosition = None
                    self.lock.release()
                # mode auswerten (1=nix, 2=2D lock, 3=3d lock)
                if mode < 2:
                    # kein GPS lock
                    self.log.debug("no gps lock. go away...")
                    self.lock.acquire()
                    self.gpsPosition = None
                    self.lock.release()
                    # hat sich das verändert zu vorher?
                    if self.isGpsLock:
                        self.isGpsLock = False
                        # gibt es einen Callback?
                        if self.callBackLockGPS is not None:
                            self.callBackLockGPS(self.isGpsLock)
                    # ein datensatz gelesen, zurück 
                    return
                # da ist GPS lock, war das vorher schon so?
                if not self.isGpsLock:
                    # nein. benachrichtigen
                    self.isGpsLock = True
                    # ist da ein Callback?
                    if self.callBackLockGPS is not None:
                        self.callBackLockGPS(self.isGpsLock)
                    # dann noch fix den Bereich der POI in der Nähe filtern
                    self.currPois = self.filter_poi_circle(self.POI, "POI")
                    self.currStops = self.filter_poi_circle(self.STOPS, "STOP")
                # jetzt die GPS Daten lesen
                self.__get_gps_pos()
            if not self.isRunning:
                return
            sleep(.5)

    def __get_gps_pos(self):
        """
        privat, position lesen und konvertieren,
        wenn eine position gelesen werden konnte, vergleichen ob ein POI
        im umkreis ist
        :return: None
        """
        if not self.isRunning:
            return
        # Daten sperren
        self.lock.acquire()
        try:
            # zugreifen auf Position mit Locking
            self.log.debug("read pos...")
            self.gpsPosition = \
                {'lat': self.gpsdDataStream.TPV['lat'],
                 'lon': self.gpsdDataStream.TPV['lon'],
                 'speed': self.gpsdDataStream.TPV['speed'],
                 'course': self.gpsdDataStream.TPV['track']}
        except:
            self.log.error("can't read position...")
            # daten entsperren
            self.lock.release()
            return
        # daten entsperren
        self.lock.release()
        #
        # zwischendurch die Liste der POI wieder eingrenzen
        # ist die Zeit bis zum nächten Punkt überschritten?
        #
        if self.watchdogTime < time():
            # TIME_TO_POIFILTER Sekunden sind wieder rum
            self.watchdogTime = time() + GeoLocationThread.TIME_TO_POIFILTER
            # lade die Liste der infrage kommenden POI neu 
            self.currPois = self.filter_poi_circle(self.POI, "POI")
            self.currStops = self.filter_poi_circle(self.STOPS, "STOPS")
        # ist die Position und ein Callback verfügbar?
        # TODO: nach der simulation wieder kommentar entfernen
        # if self.callBackHitLocation is None:
        # kein Callback verfügbar, dann spare ich mir den Rest
        #     return
        # Also dann versuche heruszufinden ob ich im Umkreis eines POI bin
        #
        # bin ich im Bereich eines POI?
        # <position>
        #    <title>Habinghorst</title>
        #    <lat>52.7086533</lat>
        #    <lon>10.2276017</lon>
        #    <radius>1000</radius>
        #    <notice>Habinghorst</notice>
        #    <medium>besondersSchoeneAussicht01.jpg</medium>
        #    <medium>besondersSchoeneAussicht02.jpg</medium>
        #    <medium>besondersSchoeneAussicht02.avi</medium>
        # </position>
        self.lock.acquire()
        myself = (self.gpsPosition["lat"], self.gpsPosition["lon"])
        self.lock.release()
        #
        # ist eine Haltestelle im Bereich bemerkt worden (Prio 1)?
        #
        if self.hitStop is not None:
            self.log.debug("check bus stop...")
            self.__is_hit_stop_in_radius(myself)
            return
        # ansonsten:
        # ist der vorhandene Punkt noch im Bereich (Prio 2)?
        # self.hitPoi ist der letze Treffer oder None
        #
        if self.hitPoi is not None:
            self.__hit_pos_in_radius(myself)
            return
        #
        # keine aktiven Bereiche
        # jetzt wieder Prio 1 die Haltestellen (Einfahrt)
        #
        for poi in self.currStops:
            poi_dest = (poi["lat"], poi["lon"])
            # Bin ich im Umkreis?
            distance = vincenty(myself, poi_dest).meters
            if distance < poi['radius']:
                # schon benachrichtigt?
                if self.hitStop is None:
                    # nein, benachrichtigen und merken
                    self.hitStop = poi
                    # Kennzeichne, ich bin noch nicht ausgefahren
                    self.hitStop["released"] = False
                    self.hitStop['arrived'] = False
                    self.log.info("HIT an bus stop area: %s distance: %d" % (poi["title"], int(distance)))
                    if self.callBackHitLocation is not None:
                        self.callBackHitLocation(poi)
                    return
                else:
                    # ein Treffer ist schon da.
                    # ist es derselbe Punkt?
                    if self.hitStop["lat"] == poi["lat"] and self.hitStop["lat"] == poi["lat"]:
                        # ist derselbe Punkt, relaxen, nix zu tun
                        return
                    else:
                        # der Treffer ist neu, gib Nachricht an das Programm
                        self.hitStop = poi
                        # Kennzeichne, ich bin noch nicht ausgefahren
                        self.hitStop["released"] = False
                        self.hitStop['arrived'] = False
                        self.log.info("HIT an new bus stop area: %s distance: %d" % (poi["title"], int(distance)))
                        if self.callBackHitLocation is not None:
                            self.callBackHitLocation(poi)
                        return
        #
        # und nun Prio 2 die anderen POI
        #
        for poi in self.currPois:
            poi_dest = (poi["lat"], poi["lon"])
            # Bin ich im Umkreis?
            distance = vincenty(myself, poi_dest).meters
            if distance < poi["radius"]:
                # schon benachrichtigt?
                if self.hitPoi is None:
                    # nein, benachrichtigen und merken
                    self.hitPoi = poi
                    self.log.info("HIT an geolocation: %s" % poi["title"])
                    if self.callBackHitLocation is not None:
                        self.callBackHitLocation(poi)
                    return
                else:
                    # ein Treffer ist schon da.
                    # ist es derselbe Punkt?
                    if self.hitPoi["lat"] == poi["lat"] and self.hitPoi["lat"] == poi["lat"]:
                        # ist derselbe Punkt, relaxen, nix zu tun
                        return
                    else:
                        # der Treffer ist neu, gib Nachricht an das Programm
                        self.hitPoi = poi
                        self.log.info("HIT an geolocation: %s" % poi["title"])
                        if self.callBackHitLocation is not None:
                            self.callBackHitLocation(poi)
                        return
                        # dann zur nächsten Runde (nächster Punkt)

    def __is_hit_stop_in_radius(self, myself):
        """
        Ist der Bus noch in der haltestelle?
        :param myself: Meine Koordinaten
        :return: Ist er noch in der haltestelle?
        """
        # da ist ein Treffer für Haltestellen aktuell, 
        # also teste mal ob das noch passt
        poi_dest = (self.hitStop["lat"], self.hitStop["lon"])
        distance = vincenty(myself, poi_dest).meters
        #
        # bin ich im engeren Kreis der Haltestelle?
        #
        if distance < GeoLocationThread.STOP_GETOUT:
            if self.hitStop["arrived"] is False:
                self.hitStop["arrived"] = True
                self.log.info("bus stop arrived, dinstance: %d" % distance )
            # ich bin noch im Bereich, alles andere kann warten
            # nichts weiter unternehmen
            return True
        #
        # bin ich irgendwo zwischen dem inneren Kreis und dem äußeren Kreis
        # aber ist self.hitStop noch aktiv
        #
        if GeoLocationThread.STOP_GETOUT < distance < self.hitStop['radius'] + 5:
            # bin noch im Bereich aber schon weg von der Haltestelle
            # Anzeige freigeben, aber HIT noch sperren
            if self.hitStop["released"] is True:
                # die haltestelle wurde wieder frei gegeben, bin aber noch im äußeren Kreis
                # also nicht weiter untenehmen
                return True
            else:
                if self.hitStop["arrived"] is True:
                    # wurde noch nicht freigegeben, aber schon aus dem inneren Kreis daher mach ich das jetzt
                    self.log.info(
                        "UNHIT an bus stop location: %s, distance: %d, bus station is lock while distance is wide enough."
                        % (self.hitStop["title"], distance))
                    self.hitStop["released"] = True
                    # teile das dem parent-Prozess mit, wenn csallback definiert wurde
                    if self.callBackHitLocation is not None:
                        self.callBackHitLocation(None)
            return True
        else:
            # ok distanz ist größer, Bereich wurde verlassen, gib Nachricht!
            self.log.info("leaved bus stop area: %s, distance: %d" % (self.hitStop["title"], distance))
            self.hitStop = None
            return False

    def __hit_pos_in_radius(self, myself):
        """
        Ist der bus noch im bereich des POI
        :param myself:
        :return: True wenn noch im Bereich des Busses, False wenn ausserhalb
        """
        # da ist ein Treffer für ein POI gewesen, 
        # also teste mal ob das noch passt
        poi_dest = (self.hitPoi["lat"], self.hitPoi["lon"])
        # bin ich noch im Bereich?
        distance = vincenty(myself, poi_dest).meters
        radius = self.hitPoi["radius"] + 50
        if distance < radius:
            # bin noch im Bereich, alles andere kann warten
            # hysterese ist 50 meter, falls das GPS schwankt würde sonst
            # ständig rein/raus zittern....
            self.log.debug("Hitted poi distance: %04d while radius : %03d (hysterese %03d)" %
                           (distance, self.hitPoi["radius"], radius))
            return True
        # ok, Bereich wurde verlassen, gib Nachricht!
        self.log.info("UNHIT an geolocation: %s" % self.hitPoi["title"])
        self.hitPoi = None
        if self.callBackHitLocation is not None:
            self.callBackHitLocation(None)
        return False

    def filter_poi_circle(self, poi_list, notice=""):
        """
        filtere aus allen POI in einem Radius (GeoLocationThread.POI_RADIUS)
        heraus. Das ist gut für die performance, ich muss nicht alle 0.5 Sekunden
        alle POI vergleichen, wenn die weiter weg sind....
        :param poi_list: Liste der POI
        :param notice: Bemerkung für debug
        :return: reduzierte Liste der POI
        """
        # Leere Liste anlegen
        m_pois = []
        # aktuelle Position lesen
        self.lock.acquire()
        myself = None
        if self.gpsPosition is not None:
            myself = (self.gpsPosition["lat"], self.gpsPosition["lon"])
        self.lock.release()
        if myself is None:
            # ok, keine Position, nichts zu tun
            return m_pois
        # Die ganze Liste durchsuchen
        for poi in poi_list:
            poi_dest = (poi["lat"], poi["lon"])
            # Bin ich im Umkreis?
            distance = vincenty(myself, poi_dest).meters
            if distance < GeoLocationThread.POI_RADIUS:
                m_pois.append(poi)
        self.log.debug("current circle of pois has %d entrys %s" % (len(m_pois), notice))
        return m_pois

    def set_pois(self, pois):
        """
        setze die Liste der POI's für den Thread
        :param pois: Liste der Points of interest
        :return: None
        """
        # Zugriff auf synchronisiert
        self.log.debug("filter pois...")
        self.lock.acquire()
        self.POI = [poi for poi in pois if poi['type'] == 'position']
        self.STOPS = [poi for poi in pois if poi['type'] == 'stop']
        #
        # sorge für einen Radius un dafür dass er korrekt ist
        #
        for poi in self.STOPS:
            try:
                # korrigiere den Radius wenn notwendig
                if poi['radius'] is None or poi['radius'] < GeoLocationThread.STOP_GETOUT:
                    # falls kein Radius definiert ist oder kleiner als der innere Bereich
                    poi['radius'] = GeoLocationThread.STOP_COMIN
            except KeyError:
                # erzeuge den Radius, wenn er fehlt
                poi['radius'] = GeoLocationThread.STOP_COMIN
        self.lock.release()
        self.log.debug("filter pois...OK")

    def get_pos(self):
        """
        gib die Liste des Thread über POI's zurück
        :return: Liste mit POI's
        """
        self.lock.acquire()
        pos = self.gpsPosition
        self.lock.release()
        return pos

    def set_on_poi_hit(self, cb_func):
        """
        setze einen Callback bei GPS Treffer
        :param cb_func: Funktion, welche als callback arbeiten soll 
        :return: None
        """
        self.callBackHitLocation = cb_func

    def clear_on_poi_hit(self):
        """lösche einen Callback bei GPS Treffer"""
        self.callBackHitLocation = None

    def set_on_gps_lock(self, cbFunc):
        """
        setze einen Callback bei GPS Lock/Unlock
        :param cbFunc: Funktion, welche als callback arbeiten soll
        :return: None
        """
        self.callBackLockGPS = cbFunc

    def clear_on_gps_lock(self):
        """lösche einen Callback bei GPS Lock/Unlock"""
        self.callBackLockGPS = None

    def get_watchdog_time(self):
        """
        Wann läuft der interne wachhund ab?
        Die Zeit wann das nächste mal die POI gefiltert werden
        plus Reserve von 3 Sekunden
        :return: Ablaufzeit
        """
        return self.watchdogTime + 3

    def make_logger(my_log_level):
        """
        Logger für debugging machen
        :return: Loglevel beim debuggen
        """
        log = logging.getLogger("geolocation")
        log.setLevel(my_log_level)
        handler = logging.handlers.RotatingFileHandler(
            GeoLocationThread.DEFAULT_LOGFILE, maxBytes=250000, backupCount=5
        )
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
        handler.setFormatter(formatter)
        log.addHandler(handler)
        return log


def geo_main():
    """
    Mainfunktion beim Debuggen
    :return: None
    """
    from ControlXmlParser import ControlXmlParser
    log = logging.getLogger("mediaplay")
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.debug("parse xml file...")
    parser = ControlXmlParser(log, "../busControl-dieter.xml")
    pois = parser.parse_control_file()
    del parser
    log.info("xml parser done...")
    gps_thread = GeoLocationThread(log, "127.0.0.1", 2947)
    gps_thread.set_pois(pois)
    #
    # INT Handler installieren (CTRL+C)
    #
    signal.signal(signal.SIGINT, lambda signal, frame: gps_thread.quit_thread())
    signal.signal(signal.SIGTERM, lambda signal, frame: gps_thread.quit_thread())
    #
    log.info("switch to info log level")
    log.setLevel(logging.INFO)
    gps_thread.start()
    log.debug("thread started (Until BREAK)....")
    gps_thread.join()
    log.debug("thread ended....")


if __name__ == '__main__':
    geo_main()
