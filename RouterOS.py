#!/usr/bin/env python

"""
http://wiki.mikrotik.com/wiki/Manual:API
http://wiki.mikrotik.com/wiki/API_command_notes
http://wiki.mikrotik.com/wiki/RouterOS_PHP_class
https://svn.ayufan.eu/svn/rosapi/trunk/
"""

import hashlib
import socket
from os.path import basename
from sys import argv, stdin
from select import select
from binascii import hexlify, unhexlify

# ------------------------------------------------------------------------------
# ApiRos
# ------------------------------------------------------------------------------

class ApiRos(object):
	"""RouterOS API"""


	def __init__(self, stream):
		self.__stream = stream
		self.verbose = False


	@property
	def verbose(self):
		return self.__verbose


	@verbose.setter
	def verbose(self, value):
		self.__verbose = value


	def login(self, username, password):
		for replay, attributes in self.talk(["/login"]):
			challenge = unhexlify(attributes['ret'])
		md = hashlib.md5()
		md.update('\x00')
		md.update(password)
		md.update(challenge)
		hash = hexlify(md.digest())
		sentence = ["/login", "=name=" + username, "=response=00" + hash]
		response = self.talk(sentence)


	def talk(self, words):
		if self.writeSentence(words) == 0:
			return
		responses = []
		while True:
			sentence = self.readSentence()
			if len(sentence) == 0:
				continue
			reply, attributes = self.__processResponse(sentence)
			responses.append((reply, attributes))
			if reply == '!done':
				return responses


	def __processResponse(self, sentence):
		reply = sentence[0]
		attributes = {}
		for word in sentence[1:]:
			equalSignIndex = word.find('=', 1)
			if (equalSignIndex == -1):
				key = word
				value = ''
			else:
				key = word[:equalSignIndex]
				value = word[equalSignIndex + 1:]
			if key[:1] == '=':
				key = key[1:]
			attributes[key] = value
		return reply, attributes


	def writeSentence(self, words):
		writeWordCount = 0
		for word in words:
			self.__writeWord(word)
			writeWordCount += 1
		self.__writeWord('')
		return writeWordCount


	def readSentence(self):
		sentence = []
		while 1:
			word = self.__readWord()
			if word == '':
				return sentence
			sentence.append(word)


	def __writeWord(self, word):
		text = 'EOF' if word == '' else word
		self.__log('<<<', text)
		self.__writeLen(len(word))
		self.__writeStr(word)


	def __readWord(self):
		word = self.__readStr(self.__readLen())
		text = 'EOF' if word == '' else word
		self.__log('>>>', text)
		return word


	def __writeLen(self, l):
		if l < 0x80:
			self.__writeStr(chr(l))
		elif l < 0x4000:
			l |= 0x8000
			self.__writeStr(chr((l >> 8) & 0xFF))
			self.__writeStr(chr(l & 0xFF))
		elif l < 0x200000:
			l |= 0xC00000
			self.__writeStr(chr((l >> 16) & 0xFF))
			self.__writeStr(chr((l >> 8) & 0xFF))
			self.__writeStr(chr(l & 0xFF))
		elif l < 0x10000000:
			l |= 0xE0000000
			self.__writeStr(chr((l >> 24) & 0xFF))
			self.__writeStr(chr((l >> 16) & 0xFF))
			self.__writeStr(chr((l >> 8) & 0xFF))
			self.__writeStr(chr(l & 0xFF))
		else:
			self.__writeStr(chr(0xF0))
			self.__writeStr(chr((l >> 24) & 0xFF))
			self.__writeStr(chr((l >> 16) & 0xFF))
			self.__writeStr(chr((l >> 8) & 0xFF))
			self.__writeStr(chr(l & 0xFF))


	def __readLen(self):
		c = ord(self.__readStr(1))
		if (c & 0x80) == 0x00:
			pass
		elif (c & 0xC0) == 0x80:
			c &= ~0xC0
			c <<= 8
			c += ord(self.__readStr(1))
		elif (c & 0xE0) == 0xC0:
			c &= ~0xE0
			c <<= 8
			c += ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
		elif (c & 0xF0) == 0xE0:
			c &= ~0xF0
			c <<= 8
			c += ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
		elif (c & 0xF8) == 0xF0:
			c = ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
			c <<= 8
			c += ord(self.__readStr(1))
		return c


	def __writeStr(self, text):
		totalSentBytes = 0
		while totalSentBytes < len(text):
			sentBytes = self.__stream.send(text[totalSentBytes:])
			if sentBytes == 0:
				raise RuntimeError, "connection closed by remote end"
			totalSentBytes += sentBytes


	def __readStr(self, length):
		text = ''
		while len(text) < length:
			data = self.__stream.recv(length - len(text))
			if data == '':
				raise RuntimeError, "connection closed by remote end"
			text += data
		return text


	def __log(self, *args):
		if self.__verbose:
			print ' '.join(map(str, args))


# ------------------------------------------------------------------------------
# RouterOS
# ------------------------------------------------------------------------------

class RouterOS(object):
	def __init__(self, address, username, password):
		self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.__sock.connect(address)
		self.__apiros = ApiRos(self.__sock)
		self.__apiros.login(username, password)
		self.__apiros.verbose = True


	def getall(self, command, args = [], proplist = []):
		return self.__send(command, 'getall', args, proplist)


	def set(self, command, args):
		return self.__send(command, 'set', args, [])


	def add(self, command, args):
		return self.__send(command, 'add', args, [])


	def __send(self, command, action, args, proplist):
		sentence = []
		if type(command) in (list, tuple):
			command = '/'.join(command)
		command = command + '/' + action
		sentence.append(command)
		if args:
			if type(args) in (list, tuple):
				for value in args:
					sentence.append(value)
			elif type(args) == dict:
				for key, value in args.items():
					sentence.append('=%s=%s' % (str(key), str(value)))
			else:
				raise TypeError('bad args type %s' % str(type(args)))
		if proplist:
			sentence.append('.proplist=' + ','.join(proplist))
		return self.__apiros.talk(sentence)


	def interactiveLoop(self):
		inputsentence = []
		while True:
			readyList = select([self.__sock, stdin], [], [], None)
			readyToRead = readyList[0]
			if self.__sock in readyToRead:
				self.__apiros.readSentence()
			if stdin in readyToRead:
				line = stdin.readline().strip()
				if line == 'quit':
					return
				if line == '':
					self.__apiros.talk(inputsentence)
					inputsentence = []
				else:
					inputsentence.append(line)


	def write(self, commands):
		return self.__apiros.talk(commands)


def main():
	if len(argv) < 4:
		program = basename(argv[0])
		print 'use: %s host username password' % program
		exit(1)

	host = argv[1]
	username = argv[2]
	password = argv[3]
	commands = argv[4:]

	address = (host, 8728)
	api = RouterOS(address, username, password)
	#api.mainLoop()
	print api.write(commands)


if __name__ == '__main__':
    main()

