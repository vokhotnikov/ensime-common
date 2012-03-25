#!/usr/bin/env python

# EnsimeClient.py
#
# Copyright (c) 2012, Jeanluc Chasseriau <jeanluc@lo.cx>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of ENSIME nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL Aemon Cannon BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import socket
import select
import time
from optparse import OptionParser

# try to find directories 'lib/common' or 'src/main/python' to import dependencies
def sourceFinder(directory):
  try: entries = os.listdir(directory)
  except: return None

  entries.sort(key=str.lower)
  entries.reverse()

  for entry in entries:
    if entry == 'src':
      return directory + '/src/main/python'

  parts = directory.split('/')
  directory = '/'.join(parts[:-1])

  return sourceFinder(directory)

directory = sourceFinder(os.path.dirname(sys.argv[0]))
if directory == None:
  print("Unable to find common python directory")
  sys.exit(1)

sys.path.append(directory)

try:
  from Helper import Logger
except:
  print("Unable to find Helper.py")
  sys.exit(1)

DEFAULT_LOG_FILENAME = 'EnsimeClient.log'

class Proxy:
  """Base class providing basic proxy features: read and write"""

  class Read:
    def __init__(self, serverSocket):
      self.serverSocket = serverSocket

    def server(self):
      try:
        hexSize = self.serverSocket.recv(6)
        size = int(hexSize, 16)
        data = self.serverSocket.recv(size)
      except Exception as e:
        Logger().error("Proxy.Read.server: unable to read data from server: " + str(e))
        return (None, None, None)
      return (size, hexSize, data)

    def stdin(self):
      try:
        data = sys.stdin.readline()
      except Exception as e:
        Logger().error("Proxy.Read.stdin: unable to read data from stdin: " + str(e))
        return None
      return data

  class Write:
    def __init__(self, serverSocket):
      self.serverSocket = serverSocket

    def server(self, data):
      try:
        self.serverSocket.sendall(data)
      except Exception as e:
        Logger().error("Proxy.Write.server: unable to send data to server: " + str(e))
        return False
      return True

    def stdout(self, data):
      try:
        sys.stdout.write(data)
        sys.stdout.flush()
      except Exception as e:
        Logger().error("Proxy.Write.stdout: unable to write data to stdout: " + str(e))
        return False
      return True

  def __init__(self, serverSocket):
    self.serverSocket = serverSocket
    self.read = self.Read(serverSocket)
    self.write = self.Write(serverSocket)

class RawProxy(Proxy):
  """Raw Proxy: without add or changes on data"""

  def __init__(self, serverSocket):
    Proxy.__init__(self, serverSocket)

  def fromServer(self):
    (size, hexSize, data) = self.read.server()
    if size == None:
      return False

    Logger().debug("server: " + hexSize + data)

    if not self.write.stdout(hexSize + data):
      return False

    return True

  def fromStdin(self):
    data = self.read.stdin()
    if data == None:
      return False

    Logger().debug("stdin: " + data)

    if not self.write.server(data):
      return False

    return True

class SwankProxy(Proxy):
  """Swank Proxy: provide abstraction of the swank protocol"""

  def __init__(self, serverSocket):
    Proxy.__init__(self, serverSocket)

  def fromServer(self):
    (size, hexSize, data) = self.read.server()
    if size == None:
      return False

    Logger().debug("server: " + hexSize + data)

    if not self.write.stdout(data + "\n"):
      return False

    return True

  def fromStdin(self):
    data = self.read.stdin()
    if data == None:
      return False

    Logger().debug("stdin: " + data)

    dataSize = "%06x" % (len(data))
    if not self.write.server(dataSize + data):
      return False

    return True

def usage():
  helplist = [
    '[-l|--log logfilename]',
    '[-f|--portfile port_filename]',
    '[-p|--port port_number]',
    '[-r|--raw]'
  ]

  print("Usage: %s %s" % (sys.argv[0], ' '.join(helplist)))
  print("")
  sys.exit(1)

def main():

  Logger().useStdOut(True)

  parser = OptionParser()
  parser.add_option('-l', '--log',
                    dest='log',
                    help='log filename')
  parser.add_option('-f', '--portfile',
                    dest='portfile',
                    help='port file to read tcp port from')
  parser.add_option('-p', '--port',
                    dest='port',
                    help='tcp port number')
  parser.add_option('-r', '--raw',
                    dest='raw',
                    action="store_true",
                    help='raw mode')

  (options, args) = parser.parse_args()

  logfile = DEFAULT_LOG_FILENAME
  if options.log != None:
    logfile = options.log

  if options.port != None:
    try: port = int(options.port)
    except:
      Logger().error("Invalid given port number ("+options.port+")")
      return 1

  elif options.portfile != None:
    try:
      f = file(options.portfile)
      port = f.readline()
      f.close()
      port = int(port)
    except:
      Logger().error("Unable to read port from: "+options.portfile)
      return 1

  else:
    usage()
    return 1

  
  addr = ("localhost", port)
  try:
    serverSocket = socket.create_connection(addr)
  except:
    Logger().error("Unable to connect to swank server "+str(addr))
    return 1

  if not Logger().setOutput(logfile):
    Logger.error("Unable to open log file")
    return 1

  Logger().useStdOut(False)
  Logger().info('-'*30)
  Logger().info(time.ctime() + ": start proxying")

  proxy = None
  if options.raw:
    proxy = RawProxy(serverSocket)
  else:
    proxy = SwankProxy(serverSocket)

  runProxy(proxy)

  serverSocket.close()

  Logger().info("done")

  return 0

def runProxy(proxy):

  def serverError():
    Logger().error("runProxy: serverError: server error")
    return False

  def stdinError():
    Logger().error("runProxy: stdinError: stdin error")
    return False

  flag = True
  input = [proxy.serverSocket, sys.stdin]
  output = []
  error = [proxy.serverSocket, sys.stdin]
  timeout = 0.1 # sec

  inputHandlers = {proxy.serverSocket: proxy.fromServer, sys.stdin: proxy.fromStdin}
  errorHandlers = {proxy.serverSocket: serverError, sys.stdin: stdinError}

  while flag:
    try:
      (i, o, e) = select.select(input, output, error, timeout)
    except BaseException as e:
      Logger().error("Handling exception: " + str(e))
      flag = False

    for ii in i:
      if not inputHandlers[ii]():
        flag = False

    for ee in e:
      if not errorHandlers[ee]():
        flag = False

if __name__ == "__main__":
  r = main()
  sys.exit(r)

