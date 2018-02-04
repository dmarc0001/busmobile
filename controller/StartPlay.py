#!/usr/bin/python3
#

import pwd
import os
import sys
import time
import logging
import logging.handlers
import signal
from pathlib import Path
from MainController import MainObject
from KodiControl import KodiException, KodiControl
from MediaControl import MediaControl

"""
TODO: mit pgrep auf kodi testen evtl killen...
"""
__author__ = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__ = 'GPL'
__version__ = '0.1'

debug = True
kodi_url = str('http://127.0.0.1:8008/jsonrpc')
usb_mount_point = str('/media/pi/mediastick')
control_file = usb_mount_point + "/busControl.xml"
log_file = "/var/log/mediaplayer/mediaplay.log"
marker_file = "/home/pi/mediaplayer/controller/x-session.mark"
socket_file = "/home/pi/mediaplayer/controller/show_display.sock"


def make_logger(my_log_level):
    """
    Erzeuge den Logger für das Programm
    :param my_log_level: Loglevel für das Programm
    :return: das Logobjekt
    """
    log = logging.getLogger("mediaplay")
    log.setLevel(my_log_level)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5000000, backupCount=5
    )
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log


def wait_for_sys_rdy(log):
    """
    Warte bis das System gestartet ist und der Stick vorhanden
    :param log: das Logobjekt des Progammes
    :return: Ist der Stick vorhanden??
    """
    log.debug("test für device ready...")
    marker_file_obj = Path(marker_file)
    if marker_file_obj.exists() & marker_file_obj.is_file():
        log.debug("Markerfile found, can start mediaplayer...")
        return True
    # nicht gefunden, eine kleine Weile testen...
    for tests in range(10):
        log.info("Markerfile not found, can't start mediaplayer. Wait (#%d)..." % tests)
        time.sleep(3)
        if marker_file_obj.exists() & marker_file_obj.is_file():
            log.debug("Markerfile found, can start mediaplayer...")
            return True
    log.fatal("Markerfile not found, can't start mediaplayer.")
    return False


def main_prog():
    """
    Das Hauptprogramm
    (in signal TERM (CTRL-C) threads stopping)
    :return: None
    """
    loglevel = logging.WARN
    if debug:
        loglevel = logging.DEBUG
    log = make_logger(loglevel)
    log.info("start player program...")
    log.debug("running as user \"%s\"" % pwd.getpwuid(os.getuid()).pw_name)
    # teste ob das system fertig gestartet ist
    if not wait_for_sys_rdy(log):
        log.error("can't find markerfile (%s), check startroutines or reboot!" % marker_file)
        return
    #
    # Mediencontroller instanzieren
    #
    media_control = MediaControl(log, kodi_url)
    #
    # mount des Sticks checken
    #
    is_mounted = media_control.check_is_mounted(usb_mount_point)
    loop_count = int(0)
    while not is_mounted:
        if not media_control.mount_usb_device(usb_mount_point):
            log.error("ERROR: can't mount usb stick, abort!")
            return
        time.sleep(3)
        is_mounted = media_control.check_is_mounted(usb_mount_point)
        if is_mounted:
            break
        loop_count += 1
        if loop_count > 5:
            log.error("ERROR: can't mount usb stick, abort!")
            return
    #
    # die Voraussetzungen sind nach definition erfüllt (ist ein test)
    # jetzt den Kodi selber bearbeiten
    #
    kodi_control = KodiControl(log, kodi_url)
    #
    # laeuft KODI schon
    #
    if kodi_control.is_kodi_running():
        # laeuft schon, alles klar
        log.info("kodi is always running...OK")
    else:
        # laeuft nicht, ich versuch mal zu starten
        if not kodi_control.app_start_kodi():
            log.info("kodi NOT started, abort...")
            # wenn nicht, schwerer Fehler... ENDE
            raise Exception("can't start kodi mediaplayer...")
            return
        log.debug("kodi started...")
    #
    # schaue mal, ob der Kodi schon antwortet
    # falls er noch hochfaehrt
    #
    loop_nr = int(0)
    while (not kodi_control.app_get_ping()) and (loop_nr < 30):
        loop_nr += 1
        time.sleep(3)
        log.debug("wait for ping from kodi...")
    try:
        version = kodi_control.app_get_json_version()
        if None is version:
            log.error("ERROR while ask for JSON version! abort...")
            del kodi_control
            del media_control
        log.debug("KODI JSON-API Version major: %s minor: %s" \
                  % (version["version"]["major"], version["version"]["minor"]))
        if int(version["version"]["major"]) < 6:
            log.error("KODI's API version is to small ( < 6 )... EXIT")
            sys.exit(2)
    except KodiException as msg:
        print(repr(msg))
        return
    #
    # das Mainobjekt macht den Rest
    #
    media_control.load_media_list(usb_mount_point, False)
    main_obj = MainObject(log, kodi_control, media_control, kodi_url, socket_file, control_file)
    signal.signal(signal.SIGINT, lambda signal, frame: main_obj.quit_app())
    # etwas warten um dem kodi noch zeit zu geben sich zu sortieren
    time.sleep(5)
    main_obj.main_loop()
    #
    # aufraumen
    #
    del kodi_control
    time.sleep(2)
    del media_control
    del main_obj
    log.info("end player program...")
    return

if __name__ == '__main__':
    main_prog()
