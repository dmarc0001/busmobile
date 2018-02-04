#!/usr/bin/python3
#
import logging
import logging.handlers
import xml.etree.ElementTree as ET

__author__ = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__ = 'GPL'
__version__ = '0.1'

log_file = "/var/log/mediaplayer/mediaplay-xml.log"
usb_mount_point = str('/media/pi/mediastick')
control_file = "/home/pi/mediaplayer/busControl.xml"


class ControlXmlParser:
    """
    Objekt zum parsen des Steuerungs-XML-Files
    """

    def __init__(self, logger, ctrl_file):
        """Konstruktor"""
        self.log = logger
        self.controlFile = ctrl_file
        self.POI = []
        self.log.debug("xml parser instantiated...")

    def __del__(self):
        """Destruktor"""
        self.log.debug("xml parser deleted...")

    def parse_control_file(self, ctrl_file=None):
        """
        Parse die datei
        :param ctrl_file: XML Steuerdatei oder None
        :return:
        """
        if ctrl_file:
            self.controlFile = ctrl_file
        self.log.debug("start parsing xml file...")
        tree = ET.parse(self.controlFile)
        self.log.debug("start parsing xml file...OK")
        xml_root = tree.getroot()
        # die Positionen in eine Liste parken
        for pos in xml_root:
            # die Listeneinträge als Dictonary erzeugen
            single_pos = {'type': pos.tag}
            media_list = []
            for item in pos:
                # einen Eintrag ins Dictonary
                if item.tag == "medium":
                    media_list.append(item.text)
                elif item.tag == "radius" or item.tag == "dir":
                    if item.text is not None:
                        single_pos[item.tag] = int(item.text)
                    else:
                        single_pos[item.tag] = -1
                else:
                    single_pos[item.tag] = item.text
            single_pos["medium"] = media_list
            # dass Dictonary in die Liste
            self.POI.append(single_pos)
        # die Liste gebe ich nun zurück
        return self.POI


def main():
    """Main zum Testen"""
    loglevel = logging.DEBUG
    log = logging.getLogger("mediaplay")
    log.setLevel(loglevel)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=250000, backupCount=5
    )
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.info("start xml parser...")
    parser = ControlXmlParser(log, control_file)
    log.debug("parse xml file...")
    pois = parser.parse_control_file()
    del parser
    log.info("xml parser done...")
    print("filter pois->position...")
    positions = [poi for poi in pois if poi['type'] == 'position']
    print("filter pois->stop...")
    stops = [poi for poi in pois if poi['type'] == 'stop']
    print("filter ok")
    print(" ")
    for item in pois:
        print(item)
    print("===========================================")
    print("==POI======================================")
    for item in positions:
        print(item)
    print("==STOP======================================")
    for item in stops:
        print(item)

if __name__ == '__main__':
    main()
