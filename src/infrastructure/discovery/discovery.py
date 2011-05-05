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

from __future__ import with_statement

from twisted.internet import reactor
from twisted.internet import task
from twisted.internet import threads
from twisted.web.server import Site
from twisted.web.resource import Resource
from boto.ec2.connection import EC2Connection
from string import Template
import pprint
import time
import threading
import collections
import copy

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

# ----------------------------------------------------------------------
# Constants not to change.
# ----------------------------------------------------------------------
AWS_LOADBALANCER_GROUP_NAME = "loadbalancer"
AWS_WEBMACHINE_GROUP_NAME = "webmachine"
AWS_RIAK_GROUP_NAME = "riak"
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Basic classes.
# ----------------------------------------------------------------------
class DataState(object):
    """ Collection of all data needed to answer questions from HTTP clients.
    This also provides a basic set of functions that helps the Twisted
    resource answer these questions.
    """
    
    # List of functions available for clients
    AVAILABLE_FUNCTIONS = set(["get_loadbalancer_ip"])
    
    def __init__(self, loadbalancer_instances, webmachine_instances, riak_instances):
        self.loadbalancer_instances = loadbalancer_instances
        self.webmachine_instances = webmachine_instances
        self.riak_instances = riak_instances
        
    def __repr__(self):
        return str(self)
        
    def get_loadbalancer_ip(self):
        """ Get the primary load balancer's public IP address.  If an AWS
        elastic IP address is pointing at it then return this instead. """
        return "testing"
        
    def __str__(self):
        output = "\nDataState\n"
        output += "\tLoadbalancer instances:\n%s\n" % (pprint.pformat(self.loadbalancer_instances), )
        output += "\tWebmachine instances:\n%s\n" % (pprint.pformat(self.webmachine_instances), )
        output += "\tRiak instances:\n%s\n" % (pprint.pformat(self.riak_instances), )
        return output

class Instance(object):
    """ Wrapper around a cloud instance. """
    def __init__(self, type, public_dns, public_ip, id, ec2_state=None, tags=None):
        self.type = type
        self.public_dns = public_dns
        self.public_ip = public_ip
        self.id = id
        self.ec2_state = ec2_state        
        self.tags = tags
        
    def __repr__(self):
        return str(self)
        
    def __str__(self):
        output = "Instance.\n"
        output += "\tType: %s\n" % (self.type, )
        output += "\tPublic DNS: %s\n" % (self.public_dns, )
        output += "\tPublic IP: %s\n" % (self.public_ip, )
        output += "\tID: %s\n" % (self.id, )
        output += "\tEC2 state: %s\n" % (self.ec2_state, )
        output += "\tTags: %s\n" % (pprint.pformat(self.tags), )
        return output
# ----------------------------------------------------------------------


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
        all_connections = [region.connect() for region in conn_root.get_all_regions()]        
        
        logger.debug("Get EC2 instances.")
        all_reservations = [reservation for connection in all_connections                          
                                        for reservation in connection.get_all_instances()]    
        loadbalancer_instances = []
        webmachine_instances = []
        riak_instances = []
        for reservation in all_reservations:
            for (container, label) in [(loadbalancer_instances, AWS_LOADBALANCER_GROUP_NAME),
                                       (webmachine_instances, AWS_WEBMACHINE_GROUP_NAME),
                                       (riak_instances, AWS_RIAK_GROUP_NAME)]:
                if any(group.id == label for group in reservation.groups):
                    logger.debug("Reservation '%s' has label '%s'" % (reservation, label))
                    for instance in reservation.instances:
                        container.append(Instance(type="aws",
                                                  public_dns=instance.public_dns_name,
                                                  public_ip=instance.ip_address,
                                                  id=instance.id,
                                                  ec2_state=instance.state,
                                                  tags=instance.tags))
        data = DataState(loadbalancer_instances=loadbalancer_instances,
                         webmachine_instances=webmachine_instances,
                         riak_instances=riak_instances)
        logger.debug("exit")
        
        # This data will be used by Twisted and shared with clients.  Try,
        # as hard as possible, to prevent any memory leaks by making a
        # deepcopy of this object before returning.
        return copy.deepcopy(data)
    
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
        logger.debug("entry. request.prepath: %s, request.postpath: %s" % (request.prepath, request.postpath))
        query = request.postpath[0]
        with self.data_lock:
            if query in self.data.AVAILABLE_FUNCTIONS:                    
                function_member = getattr(self.data, query)
                result = function_member()
            else:
                # TODO error handling
                result = None
        return "%s" % (result, )

if __name__ == "__main__":
    root = Resource()
    root.putChild("data", DataPage())
    factory = Site(root)
    reactor.listenTCP(8880, factory)
    logger.info("running")
    reactor.run()
