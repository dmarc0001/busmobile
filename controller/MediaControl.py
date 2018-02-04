#!/usr/bin/python3
#
# Kontrolle des Mediensticks

import subprocess
import os
import re
import logging
from pathlib import Path

__author__ = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__ = 'GPL'
__version__ = '0.1'


class MediaControl:
    """
    Klasse zur Medienkontrolle
    Findet Medien, mountet/unmountet den Mediastick
    """
    # einige Reguläre Ausdrücke zum Finden von Dateien
    rxMedia = re.compile(".*\\.(bmp|png|tiff|jpg(e)?|avi|mp4|mp2|ts|mpeg|mkv)$", re.IGNORECASE)
    rxVideo = re.compile(".*\\.(avi|mp4|mp2|ts|mpeg|mkv)$", re.IGNORECASE)
    rxPicture = re.compile(".*\\.(bmp|png|tiff|jpg(e)?)$", re.IGNORECASE)

    def __init__(self, logger=None, url="http://localhost:8080/jsonrpc"):
        """
        Konstruktor
        :param logger: Logobjekt des Programmes
        :param url: KODI URL zur JSON API
        """
        self.log = logger
        self.url = url
        self.mediaDir = str()
        self.mediaList = []
        self.log.debug("init...")

    def check_symlink(self, symlink):
        """
        symlink zum Mediengerät testen
        :param symlink: symlink zum testen
        :return: Erfolgreich (vorhanden)?
        """
        # gibt es den Symlink?
        symlink_file = Path(symlink)
        if symlink_file.exists() & symlink_file.is_symlink():
            self.log.debug("symlink %s exists and is an symlink" % symlink)
            return True
        else:
            self.log.warn("symlink %s NOT exists or is not symlink" % symlink)
            return False

    def check_file_exist(self, file_name):
        """
        existiert eine Datei?
        :param file_name: Datei zum testen
        :return: existiert eine Datei??
        """
        # gibt es die Datei?
        this_file = Path(file_name)
        if this_file.exists() & this_file.is_file():
            self.log.debug("file %s exists and is an file" % file_name)
            return True
        else:
            self.log.warn("file %s NOT exists or is not file" % file_name)
            return False

    def check_is_mounted(self, mountpoint):
        """
        Moint checken
        :param mountpoint: der Mountpoint zum testen
        :return: ist gemountet oder nicht
        """
        self.log.debug("check mountpoint: %s" % mountpoint)
        #
        # frage das Sysetem nach mounts
        #
        proc = subprocess.Popen(['df', '-l', '-P'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1, err = proc.communicate()
        pattern = str(p1)
        #
        # filtere nach meinem mountpoint
        #
        if pattern.find(mountpoint) > -1:
            self.log.debug("mounted volume %s found..." % mountpoint)
            return True
        else:
            self.log.debug("mounted volume %s NOT found..." % mountpoint)

    def mount_usb_device(self, mount_point):
        """
        Versuche Stick zu mounten
        :param mount_point:
        :return:
        """
        self.log.debug("try mount mediastick fo %s..." % mount_point)
        if 0 < subprocess.call(['/bin/mount', mount_point]):
            return False
        return True

    def load_media_list(self, file_path, is_recursive):
        """
        lese Medienliste nichtrekusriv/recursiv vom Datenträger
        zurueck Liste aller gefundenen Dateinamen in relativen Pfaden
        :param file_path: Pfad, in dem gesucht wird
        :param is_recursive: rekursiv suchen oder nur dieses Verzeichnis?
        :return: Liste mit Mediendateien
        """
        self.mediaList = []
        self.mediaDir = file_path
        self.log.debug("load medialist from device %s..." % file_path)
        rawfile_names = os.listdir(file_path)
        for fileName in rawfile_names:
            if self.rxMedia.match(fileName):
                if self.check_file_exist("%s/%s" % (file_path, fileName)):
                    self.mediaList.append(fileName)
        self.mediaList.sort()
        # TODO: Recursiv machen
        # for root, dirs, files in os.walk( file_path ):
        #    print("dir: %s files: %s" %(root,files) )
        #    fileNames = filter( self.rx.match, files )
        self.log.debug("load medialist from device %s...OK" % file_path)
        return self.mediaList

    def get_media_list(self):
        """
        Liste der Medien zurueckgeben
        :return: Liste mit Mediendatien
        """
        return self.mediaList

    def get_media_dir(self):
        """
        Media-rootdir zurueck geben
        :return: Verzeichnis mit media-Dateien
        """
        return self.mediaDir

    def get_poi_media_dir(self):
        """
        Verzeichnis für POI-Mediadateien zurückgeben
        :return: Verzeichnis mit poi media dateien
        """
        return "%s/POI" % self.mediaDir

    def class_of_media(self, file_name):
        """
        Klassifiziere anhand der Endung den Dateityp nach Bild/Video
        return "picture" oder "video".
        Genau (z.B mit file XXX) ist hier zu teuer
        :param file_name: Dateiname
        :return: Typ der Datei
        """
        type_of_media = "unknown"
        self.log.debug("class_of_media test for %s..." % file_name)
        if self.rxVideo.match(file_name):
            type_of_media = "video"
        if self.rxPicture.match(file_name):
            type_of_media = "picture"
        self.log.debug("class_of_media test is %s..." % type_of_media)
        return str(type_of_media)
