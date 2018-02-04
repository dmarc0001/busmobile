#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# usage: gegps [-i] [-d kmldir]
#
# Feed location data from a running GPSD to a Google Earth instance.
# The -d argument is the location of the Google Earth installation
# directory.  If not specified, it defaults to the current directory.
#
# If you have the free (non-subscription) version, start by running with
# the -i option to drop a clue in the Google Earth installation directory,
# as 'Open_in_Google_Earth_RT_GPS.kml', then open that file in Places
# (File > Open...),
#
# The basic recipe is here:
# http://tjworld.net/wiki/Linux/Ubuntu/GoogleEarthPlusRealTimeGPS
#
# This code originally by Jaroslaw Zachwieja and a guy referring
# to himself/herself as TJ(http://tjworld.net)
# Modified by Chen Wei <weichen302@aol.com> for use with gpsd
# Cleaned up and adapted for the GPSD project by Eric S. Raymond.

import sys
import os
import getopt
from time import sleep
from threading import Thread, Lock
import signal
import logging
from GpsdConnect import GPSDSocket, DataStream


class GoogleEarthPs(Thread):
    """
    Objekt zum auslesen des GPS und bereitstellen für Google Earth Pro
    """

    HOST = '127.0.0.1'
    GPSD_PORT = 2947
    PROTOCOL = 'json'
    DEFAULT_RANGE = '800.0'

    def __init__(self, lg, kdir, host=HOST, port=GPSD_PORT):
        Thread.__init__(self)
        self.isRunning = False
        self.log = lg
        self.log.debug("create GoogleEarthPs object...OK")
        self.kmldir = kdir
        # google earth parameter
        self.range = GoogleEarthPs.DEFAULT_RANGE
        self.kml_template = GoogleEarthPs.__getkml_template()
        # gpsd sachen
        self.gpsdHost = host
        self.gpsdPort = port
        self.gpsdSocket = GPSDSocket(self.log)
        self.gpsdDataStream = DataStream(self.log)
        self.gpsPosition = None
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
                self.gpsPosition = None
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
                    self.gpsPosition = None
                # mode auswerten (1=nix, 2=2D lock, 3=3d lock)
                if mode < 2:
                    # kein GPS lock
                    self.log.debug("no gps lock. go away...")
                    self.gpsPosition = None
                    return
                # da ist GPS lock, war das vorher schon so?
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
        try:
            # zugreifen auf Position mit Locking
            self.log.debug("read pos...")
            self.gpsPosition = \
                {'lat': self.gpsdDataStream.TPV['lat'],
                 'lon': self.gpsdDataStream.TPV['lon'],
                 'speed': self.gpsdDataStream.TPV['speed'],
                 'course': self.gpsdDataStream.TPV['track'],
                 'alt': self.gpsdDataStream.TPV['alt']}
        except:
            self.log.error("can't read position...")
            return
        # KML machen
        # http://code.google.com/apis/kml/documentation/kmlreference.html
        # for official kml document
        latitude = self.gpsPosition['lat']
        longitude = self.gpsPosition['lon']
        speed_in = self.gpsPosition['speed']  # meter/second
        speed = speed_in * 3.6  # Km/h
        heading = int(round(self.gpsPosition['course'], 0))
        altitude = self.gpsPosition['alt']
        if speed < 1:
            heading = 0
        speed = "{0:03.1f}".format(speed_in * 3.6)  # Km/h
        kml_content = self.kml_template % (
            speed, heading, longitude, latitude, self.range, longitude, latitude, altitude)
        fh = open(os.path.join(self.kmldir, 'Realtime_GPS.kml'), 'w')
        fh.write(kml_content)
        fh.close()

    @staticmethod
    def __getkml_template():
        fh = open('realtime-template.xml', 'r')
        template = fh.read(2048)
        fh.close()
        # template  = "<kml xmlns=\"http://earth.google.com/kml/2.0\">\n"
        # template += "<Placemark>\n"
        # template += "    <name>%s km/h,Richtung %s Grad</name>\n"
        # template += "    <description>Realtime GPS feeding</description>\n"
        # template += "    <LookAt>\n"
        # template += "        <longitude>%s</longitude>\n"
        # template += "        <latitude>%s</latitude>\n"
        # template += "    </LookAt>\n"
        # template += "    <Point>\n"
        # template += "        <coordinates>%s,%s,%s</coordinates>\n"
        # template += "    </Point>\n"
        # template += "</Placemark>\n"
        # template += "</kml>\n"
        return template

    @staticmethod
    def make_init_file():
        template = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        template += "<kml xmlns=\"http://earth.google.com/kml/2.2\">\n"
        template += "<NetworkLink>\n"
        template += "	<name>Realtime GPS</name>\n"
        template += "	<open>1</open>\n"
        template += "	<Link>\n"
        template += "		<href>Realtime_GPS.kml</href>\n"
        template += "		<refreshMode>onInterval</refreshMode>\n"
        template += "	</Link>\n"
        template += "</NetworkLink>\n"
        template += "</kml>\n"
        return template


def make_logger(my_log_level):
    """
    Logger für debugging machen
    :return: Loglevel beim debuggen
    """
    log = logging.getLogger("geolocation")
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.setLevel(my_log_level)
    return log


if __name__ == "__main__":
    # Verzeichnis voreinstellen
    kmldir = "C:/DATEN/Download"
    # kmldir = "."
    # init fuer google earth (ohne pro)
    initialize = False
    (options, arguments) = getopt.getopt(sys.argv[1:], "d:i")
    for (opt, arg) in options:
        if opt == '-d':
            kmldir = arg
        elif opt == '-i':
            initialize = True
    # logger machen
    log = make_logger(logging.DEBUG)

    if initialize:
        f = open(os.path.join(kmldir, 'Open_in_Google_Earth_RT_GPS.kml'), 'w')
        f.write(GoogleEarthPs.make_init_file())
        log.info("google earth initialized")
        f.close()
    else:
        gegps = GoogleEarthPs(log, kmldir)
        #
        # INT Handler installieren (CTRL+C)
        #
        signal.signal(signal.SIGINT, lambda signal, frame: gegps.quit_thread())
        signal.signal(signal.SIGTERM, lambda signal, frame: gegps.quit_thread())
        #
        # log.setLevel(logging.INFO)
        gegps.start()
        log.debug("thread started (Until BREAK)....")
        gegps.join()
        log.info("thread endet...")
# end
