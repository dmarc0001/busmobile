# -*- coding: utf-8 -*-
import socket
import os

socketFile = "/home/pi/mediaplayer/controller/ipc.sock"

print("Connecting...")
if os.path.exists(socketFile):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    client.connect(socketFile)
    print("Ready.")
    print("Ctrl-C to quit.")
    print("Sending 'DONE' shuts down the server and quits.")
    while True:
        try:
            x = input("> ")
            if "" != x:
                print("SEND:", x)
                client.send(x.encode('utf-8'))
                if "DONE" == x:
                    print("Shutting down.")
                    break
        except KeyboardInterrupt as k:
            print("Shutting down.")
            client.close()
            break
else:
    print("Couldn't Connect!")
    print("Done")