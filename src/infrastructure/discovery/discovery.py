#!/usr/local/bin/python

# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/discovery/discovery.py
#
# Simple HTTP service that answers questions about cloud
# infrastructure, e.g. what the current load balancer's IP is.
# ----------------------------------------------------------------------

from twisted.internet import reactor
from twisted.internet import task
from twisted.internet import threads
from twisted.web.server import Site
from twisted.web.resource import Resource
from boto.ec2.connection import EC2Connection
import pprint
import time
import threading

APP_NAME = "discovery"
import logging
logger = logging.getLogger('discovery')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger('discovery')

class DataPage(Resource):
    isLeaf = True
    def __init__(self):
        self.data = None
        self.data_lock = threading.Lock()
        self.default_interval = 10
        self.start_data_collection()        
        Resource.__init__(self)        
    
    def get_data(self):
        logger = logging.getLogger("%s.get_data" % (APP_NAME, ))
        logger.debug("entry")
        logger.debug("Get EC2 connections.")
        conn_root = EC2Connection()                
        regions = [region.connect() for region in conn_root.get_all_regions()]        
        data = pprint.pformat(regions)                                
        logger.debug("exit")
        return data
    
    def start_data_collection(self):
        logger = logging.getLogger("%s.start_data_collection" % (APP_NAME, ))    
        logger.debug("entry")    
        d = threads.deferToThread(self.get_data)
        d.addCallback(self.process_new_data)
        d.addErrback(self.handle_data_error)
        logger.debug("exit.")
        
    def process_new_data(self, d):
        logger = logging.getLogger("%s.process_new_data" % (APP_NAME, ))            
        with self.data_lock:
            self.data = d
            logger.debug("Data is now: %s" % (self.data, ))
        reactor.callLater(self.default_interval, self.start_data_collection)
        
    def handle_data_error(self, failure):
        logger = logging.getLogger("%s.handle_data_error" % (APP_NAME, ))
        logger.error("Error occurred.\n%s" % (failure.getTraceback(), ))
        reactor.callLater(self.default_interval, self.start_data_collection)
    
    def render_GET(self, request):
        logger = logging.getLogger("%s.render_GET" % (APP_NAME, ))                    
        with self.data_lock:
            return "<html><body>%s</body></html>" % (self.data, )

if __name__ == "__main__":
    root = Resource()
    root.putChild("data", DataPage())
    factory = Site(root)
    reactor.listenTCP(8880, factory)
    logger.info("running")
    reactor.run()
