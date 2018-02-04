#!/usr/bin/python3
#
import time
import sys
import signal
import re
import threading
import logging
import logging.handlers
from time import sleep
from IpcUnixThreadedServer import IpcUnixThreadedServer
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import RPi.GPIO as GPIO
from datetime import *
import TaskWindow_auto

__author__ = 'Dirk'
__copyright__ = 'Copyright 2017'
__license__ = 'GPL'
__version__ = '0.2'

"""
2nd Screen Anzeige für den Fahrer
"""

logFile = "/var/log/mediaplayer/taskwindow.log"
socketFile = "/home/pi/mediaplayer/controller/show_display.sock"


class TaskWindow(QMainWindow, TaskWindow_auto.Ui_TaskWindow):
    """
    Klasse für das Hauptfenster (ein QT Fenster)
    """
    # Konstanten für Display-Keys
    KEY_01 = 12
    KEY_02 = 16
    KEY_03 = 18
    HEADLINE = "ANZEIGE STATUS"
    # Reguläre Ausdrücke vorcompiliert, Objektglobal
    rxTitle = re.compile(r"^title:.*", re.IGNORECASE)
    rxInfo = re.compile(r"^info:.*", re.IGNORECASE)
    rxClear = re.compile(r"^clear$", re.IGNORECASE)
    rxGpsUnlock = re.compile(r"^unlock$", re.IGNORECASE)
    rxGpsLock = re.compile(r"^lock$", re.IGNORECASE)
    rxGpsUndef = re.compile(r"^undef$", re.IGNORECASE)
    rxQuit = re.compile(r"^quit$", re.IGNORECASE)
    rxDP = re.compile(r':')

    def __init__(self, _logging, _s_file):
        """Konstruktor"""
        # logging
        self.log = _logging
        self.socketFile = _s_file
        self.log.debug("initialize TaskWindow...")
        #
        # initialisiere key-Variablen
        #
        self.key01 = False
        self.key02 = False
        self.key03 = False
        # GPS Zeit unterwegs...
        self.gps_is_lock = False
        self.timer = None
        #
        # Fenster/GUI initialisieren
        #
        self.log.debug("initialize MainWindow...")
        super(self.__class__, self).__init__()
        self.setupUi(self)  # gets defined in the UI file
        self.infoLabel.setText("init...")
        self.haedLabel.setText(TaskWindow.HEADLINE)
        # Paletten für Widgets erzeugen
        self.paletteInactiv = QPalette()
        self.paletteActiv = QPalette()
        self.paletteBackground = self.mainWidget.palette()
        self.paletteGpsNoLock = QPalette()
        self.paletteGpsLock = QPalette()
        self.paletteKeyHit = QPalette()
        self.paletteInactiv.setColor(QPalette.Background, Qt.yellow)
        self.paletteActiv.setColor(QPalette.Background, Qt.green)
        self.paletteGpsNoLock.setColor(QPalette.Background, Qt.lightGray)
        self.paletteGpsLock.setColor(QPalette.Background, Qt.green)
        self.paletteKeyHit.setColor(QPalette.Background, Qt.red)
        self.key01_indicator.setPalette(self.paletteInactiv)
        self.key02_indicator.setPalette(self.paletteInactiv)
        self.key03_indicator.setPalette(self.paletteActiv)
        self.key01_indicator.setAutoFillBackground(True)
        self.key02_indicator.setAutoFillBackground(True)
        self.key03_indicator.setAutoFillBackground(True)
        self.keyWidgetCase.setAutoFillBackground(True)
        #
        # GPIO iniialisieren für die TASTEN
        #
        self.log.debug("initialize GPIO...")
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.KEY_01, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.KEY_02, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.KEY_03, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        #
        # neu 20170822: Interrups für KEY einbauen
        #
        GPIO.add_event_detect(self.KEY_01, GPIO.BOTH,
                              callback=lambda ch: self.__pressed_on_button_slot(self.KEY_01, self.key01_indicator,
                                                                                GPIO.input(self.KEY_01)), bouncetime=10)
        GPIO.add_event_detect(self.KEY_02, GPIO.BOTH,
                              callback=lambda ch: self.__pressed_on_button_slot(self.KEY_02, self.key02_indicator,
                                                                                GPIO.input(self.KEY_02)), bouncetime=10)
        GPIO.add_event_detect(self.KEY_03, GPIO.BOTH,
                              callback=lambda ch: self.__pressed_on_button_slot(self.KEY_03, self.key03_indicator,
                                                                                GPIO.input(self.KEY_03)), bouncetime=10)
        # und GUI-Elemente initialisieren
        self.__pressed_on_button_slot(self.KEY_01, self.key01_indicator, GPIO.input(self.KEY_01))
        self.__pressed_on_button_slot(self.KEY_02, self.key02_indicator, GPIO.input(self.KEY_02))
        self.__pressed_on_button_slot(self.KEY_03, self.key03_indicator, GPIO.input(self.KEY_03))
        #
        # Unix-Socket Server erzeugen
        #
        self.msgServer = IpcUnixThreadedServer(self.log, self.socketFile)
        self.msgServer.set_on_recive(self.rec_message)
        # Sperre für das Zugreifen auf die GUI
        self.lock = threading.Lock()
        self.msgServer.start()
        self.infoLabel.setText("bereit für Anwendung...")
        self.timeLabel.setText("--:--")
        self.start_timer()

    def __del__(self):
        """DESTRUKTOR"""
        self.log.debug("destructor...")
        self.msgServer.quit_thread()
        try:
            if self.timer is not None:
                self.timer.stop()
                self.timer.deleteLater()
        except Exception:
            pass
        try:
            # Key Interrupts abschalten
            GPIO.remove_event_detect(self.KEY_01)
            GPIO.remove_event_detect(self.KEY_02)
            GPIO.remove_event_detect(self.KEY_03)
        except Exception:
            pass
        self.log.info("quit app...")
        GPIO.cleanup()

    def start_timer(self):
        """
        stsarte den Timer
        :return:
        """
        if self.timer is not None:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.__timer_handler)
        self.timer.start(2500)

    def quit_app(self):
        """Reaktion auf SIGKILL"""
        self.log.info("stop message server thread...")
        self.msgServer.quit_thread()
        self.haedLabel.setText(TaskWindow.HEADLINE)
        self.infoLabel.setText("beende Anzeige...")
        self.msgServer.join()
        sleep(3)
        QCoreApplication.quit()

    def __timer_handler(self):
        """
        Timer zyklisch abarbeiten
        :return:
        """
        if self.gps_is_lock:
            # da kann man davon ausgehen, die Zeit stimmt
            _curr_time = datetime.today()
            self.timeLabel.setText("{:%H:%M}".format(_curr_time))

    def __pressed_on_button_slot(self, bcmpin, indicator, val):
        """
        Aktion, wenn Taste betätigt wird (drücken oder loslassen)
        :param bcmpin: channel (Taste)
        :param indicator: der Indikator auf dem Display
        :param val: Wert der Taste
        :return: None
        """
        if not val:
            indicator.setPalette(self.paletteKeyHit)
            self.log.debug("key {} pressed!".format(bcmpin))
        else:
            indicator.setPalette(self.paletteInactiv)
            self.log.debug("key {} released!".format(bcmpin))

    def rec_message(self, msg_str):
        """
        Callback für Messageserver
        :param msg_str: Die Nachricht
        :return: None
        """
        self.log.info("recice: %s" % msg_str)
        try:
            self.lock.acquire()
            if self.rxTitle.match(msg_str):
                kdo, msg = self.rxDP.split(msg_str)
                self.haedLabel.setText(msg)
            elif self.rxInfo.match(msg_str):
                kdo, msg = self.rxDP.split(msg_str)
                self.infoLabel.setText(msg)
            elif self.rxClear.match(msg_str):
                self.haedLabel.setText("IDLE")
                self.infoLabel.setText("")
                self.timeLabel.setText("--:--")
            elif self.rxGpsUnlock.match(msg_str):
                self.keyWidgetCase.setPalette(self.paletteGpsNoLock)
                self.gps_is_lock = False
                self.timeLabel.setText("--:--")
            elif self.rxGpsLock.match(msg_str):
                self.keyWidgetCase.setPalette(self.paletteGpsLock)
                self.gps_is_lock = True
            elif self.rxGpsUndef.match(msg_str):
                self.keyWidgetCase.setPalette(self.paletteBackground)
                self.gps_is_lock = False
                self.timeLabel.setText("--:--")
            elif self.rxQuit.match(msg_str):
                self.quit_app()
        finally:
            self.lock.release()


def main():
    """
    Das Hauptprogramm
    :return:
    """
    # logging erzeugen
    log = logging.getLogger("TaskWindows")
    log.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        logFile, maxBytes=250000, backupCount=5
    )
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    #
    # os.environ["DISPLAY"] = ":0.1"
    # Eine Instanz des Fensters
    app = QApplication(sys.argv)
    form = TaskWindow(log, socketFile)
    #
    # INT Handler installieren (CTRL+C)
    #
    log.debug("init signalhandling...")
    signal.signal(signal.SIGINT, lambda _signal, _frame: form.quit_app())
    signal.signal(signal.SIGTERM, lambda _signal, _frame: form.quit_app())
    # Formular anzeigen
    log.debug("show form...")
    form.show()
    # Beenden des Scriptes, wenn das Hauptfenster geschlossen wird.
    log.debug("exec show form...")
    sys.exit(app.exec_())


# Als Hauptprogramm auszuführen
if __name__ == "__main__":
    main()
