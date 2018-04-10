import SocketServer
from threading import Thread
from select import select
import socket
import sys
import time
import base64

class ThreadManager:
	
	def __init__(self, basePort):
		self.basePort = basePort
		self.portCount = 0
		self.threadPool = []

	def addThread(self, httpclient, eptype="ews"):
		# check for deads
		self.threadPool = [x for x in self.threadPool if not x.dead]
		print dir(httpclient.session.sock)
		self.portCount += 1
		sc = ServerThread(self.basePort + self.portCount, httpclient, eptype=eptype)
		sc.start()
		self.threadPool.append(sc)
		

"""
Thread to listen for single connection on a given port and forward it to 
given NTLM authenticated socket

"""
class ServerThread(Thread):
	def __init__(self, port, HttpClient, eptype="ews"):
		self.type = eptype
		self.port = port
		self.client = HttpClient
		self.clientSocket = HttpClient.session.sock
		self.dead = False
		self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	def doHeartBeat(self):
		if self.type == "ews":
			header = """
POST /EWS/Exchange.asmx HTTP/1.1
Host: mail.serverchoice.com
Keep-Alive: 1000
Content-Type: text/xml
"""

			payload = """
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
<soap:Body>
<SyncFolderHierarchy  xmlns="http://schemas.microsoft.com/exchange/services/2006/messages">
<FolderShape>
<t:BaseShape>AllProperties</t:BaseShape>
</FolderShape>
<SyncState>""" 
			payload += """</SyncState>
</SyncFolderHierarchy>
</soap:Body>
</soap:Envelope>
		"""
			payload = payload.strip()
			header += "Content-Length: " + str(len(payload)) + "\n\n" + payload
			self.clientSocket.send(header)
			data = self.clientSocket.recv(4096)
			if len(data) == 0:
				print "ERROR! heartbeat received nothing"
		else:
			print "no support for mapi heartbeat yet"

		
	
	def start(self):
		print "starting server on 127.0.0.1:%i" % (self.port)
		self.server.bind(("127.0.0.1", self.port))
		self.server.listen(1)
		self.socketList = [self.server, self.clientSocket]
		self.channels = {}
		self.checkins = 0
		while not self.dead:
			inputready, outputready, exceptready = select(self.socketList, [], [], 5)
			self.checkins += 1
			if self.checkins >= 10:
				print "do heartbeat"
				self.doHeartBeat()
				self.checkins = 0
			for self.s in inputready:
				if self.s == self.server:
					serverSock, clientAddr = self.server.accept()
					self.socketList.append(serverSock)
					self.channels[serverSock] = self.clientSocket		
					self.channels[self.clientSocket] = serverSock
					print "accepting server conn from %s" % clientAddr[0]
					break
				data = ""
				# receive data from the socket, pipe it to the other socket
				try:
					data = self.s.recv(104096)
					if self.s in self.channels.keys():
						self.channels[self.s].send(data)
				except:
					# oh noes!	
					print sys.exc_info()[0]

				if len(data) == 0:
					# if the clientSocket disconnected then we have a problem, it means the target
					# killed us and needs re-relaying		
					if self.s == self.clientSocket:
						print "Big error! we got disconnected from the target" 
						self.dead = True
					else:
						print "Client disconnected.. "
						self.channels.clear()
						self.socketList = [self.server, self.clientSocket]
						
					break
