#!/usr/bin/python3
# coding=utf-8

import os
import threading
import signal
import socket
import logging
import logging.handlers

log_file = "/var/log/mediaplayer/ipcserver_thread.log"
socket_file = "/home/pi/mediaplayer/controller/ipc.sock"


class IpcUnixThreadedServer(threading.Thread):
    """
    KLasse für die Interprozesskommunikation (Hauptprogram mit
    zweitdisplay)
    """

    def __init__(self, logger, sock_file):
        """
        Konstruktor
        :param logger: der Programmlogger 
        :param sock_file: Der Kommunikationssockel
        """
        threading.Thread.__init__(self)
        self.log = logger
        self.log.debug("constructor...")
        self.uSockFile = sock_file
        self.eventCallback = None
        self.isRunning = False

    def __del__(self):
        """Destruktor"""
        self.log.debug("destructor...")
    
    def quit_thread(self):
        """Thread beenden"""
        self.log.info("== initiate unix-socket-server-thread shutdown...==")
        self.isRunning = False

    def is_thread_running(self):
        """
        sollte der Thread laufen
        :return: Ja/Nein
        """
        return self.isRunning

    def run(self):
        """Hauptschleife des Threads"""
        self.isRunning = True
        #
        if os.path.exists(self.uSockFile):
            os.remove(self.uSockFile)
        self.log.debug("Opening server socket...")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # blockend mit TIMEOUT damit der thread beendet werden kann
        server.setblocking(True)
        server.settimeout(0.2)
        server.bind(self.uSockFile)
        self.log.info("listening...")
        # Hauptschleife  
        while self.isRunning:
            # empfange Daten (blockierend mit timeout)
            try:
                datagram = server.recv(1024)
            except socket.timeout:
                continue
            if not datagram:
                continue
            else:
                message = datagram.decode('utf-8')
                self.log.debug(message)
                if self.eventCallback is not None:
                    self.eventCallback(message)
        self.log.info("Unix socket shutting down...")
        server.close()
        os.remove(self.uSockFile)

    def set_on_recive(self, callback):
        """
        Setzte einen Event-Callback
        :param callback:
        :return:
        """
        self.eventCallback = callback


def on_recive(msg):
    """
    Callback beim Debuggen
    :param msg: Nachricht
    :return: None
    """
    print("MESSAGE: %s" %msg )


def server_main():
    """Main beim debuggen"""
    log = logging.getLogger("mediaplay")
    log.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=250000, backupCount=5
    )
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(module)s: %(message)s", '%Y%m%d %H:%M:%S')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    
    server_thread = IpcUnixThreadedServer(log, socket_file)
    server_thread.set_on_recive(on_recive)
    #
    # INT Handler installieren (CTRL+C)
    #
    signal.signal(signal.SIGINT, lambda signal, frame: server_thread.quit_thread())
    signal.signal(signal.SIGTERM, lambda signal, frame: server_thread.quit_thread())
    #
    server_thread.start()
    log.debug("thread started (Until BREAK)....")
    server_thread.join()
    log.debug("thread ended....")

if __name__ == '__main__':
    server_main()
