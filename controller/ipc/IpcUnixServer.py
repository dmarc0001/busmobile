# -*- coding: utf-8 -*-
import socket
import os

socketFile = "/home/pi/mediaplayer/controller/ipc.sock"

if os.path.exists(socketFile):
    os.remove(socketFile)

print("Opening socket...")
server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
server.bind(socketFile)
server.setblocking(True)
server.settimeout(0.2)

print("Listening...")
while True:
    try:
        datagram = server.recv(1024)
    except socket.timeout:
        continue
    if not datagram:
        print(".")
        break
    else:
        print("-" * 20)
        print(datagram.decode('utf-8'))
        if "DONE" == datagram.decode('utf-8'):
            break
print("-" * 20)
print("Shutting down...")
server.close()
os.remove(socketFile)
print("Done")