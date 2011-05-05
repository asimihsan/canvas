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
import types
import json
import platform

# ----------------------------------------------------------------------
# Constants not to change.
# ----------------------------------------------------------------------
AWS_LOADBALANCER_GROUP_NAME = "loadbalancer"
AWS_WEBMACHINE_GROUP_NAME = "webmachine"
AWS_RIAK_GROUP_NAME = "riak"

APP_NAME = "discovery"

LOG_PATH = r"/home/ubuntu/canvas/log"
# ----------------------------------------------------------------------

import logging
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

if platform.system() == "Linux":
    if not os.path.isdir(LOG_PATH):
        os.makedirs(LOG_PATH)
    fh = logging.handlers.RotatingFileHandler(os.path.join(LOG_PATH, '%s.log' % (APP_NAME, )), maxBytes=10000000, backupCount=5)
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    
logger = logging.getLogger(APP_NAME)

# ----------------------------------------------------------------------
# Basic classes.
# ----------------------------------------------------------------------
class DataState(object):
    """ Collection of all data needed to answer questions from HTTP clients.
    This also provides a basic set of functions that helps the Twisted
    resource answer these questions.
    """
    
    # List of functions available for clients
    AVAILABLE_FUNCTIONS = set(["enable_verbose_logging",
                               "disable_verbose_logging",
                               "ping",
                               "get_public_ip_primary_loadbalancer",
                               "get_all_instances"])
    
    def __init__(self, loadbalancer_instances, webmachine_instances, riak_instances):
        self.loadbalancer_instances = loadbalancer_instances
        self.webmachine_instances = webmachine_instances
        self.riak_instances = riak_instances
        
    def __repr__(self):
        return str(self)
        
    def __str__(self):
        output = "\nDataState\n"
        output += "\tLoadbalancer instances:\n%s\n" % (pprint.pformat(self.loadbalancer_instances), )
        output += "\tWebmachine instances:\n%s\n" % (pprint.pformat(self.webmachine_instances), )
        output += "\tRiak instances:\n%s\n" % (pprint.pformat(self.riak_instances), )
        return output        
        
    def ping(self):
        """ Return pong.  Just prove that ths server is responsive. """
        return "pong"        
        
    def enable_verbose_logging(self):
        """ Change the logging level to DEBUG. """
        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.DEBUG)
        return "logging now at level DEBUG"
        
    def disable_verbose_logging(self):
        """ Change the logging level to INFO. """
        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.INFO)
        return "logging now at level INFO"
        
    def _get_primary_load_balancer_instance(self):
        """ Get the primary load balancer instance. If this returns
        a string then an error occurred, else returns an Instance."""
        running_loadbalancers = [instance for instance in self.loadbalancer_instances if instance.activation_state == "running"]
        if len(running_loadbalancers) == 0:
            return "ERROR DataState get_ip_primary_loadbalancer: There are no loadbalancer instances running."
        if not any("PRIMARY" in tags for instance in running_loadbalancers
                                     for tags in instance.tags):
            return "ERROR DataState get_ip_primary_loadbalancer: No running loadbalancer instance has a 'PRIMARY' tag key"
        primary_loadbalancers = [instance for instance in running_loadbalancers
                                 if instance.tags.get("PRIMARY", None) == "true"]
        if len(primary_loadbalancers) > 1:
            return "ERROR DataState get_ip_primary_loadbalancer: There is more than one primary loadbalancer instance"
        primary_loadbalancer = primary_loadbalancers[0]    
        return primary_loadbalancer        
        
    def get_public_ip_primary_loadbalancer(self):
        """ Get the primary load balancer's public IP address. """
        primary_loadbalancer = self._get_primary_load_balancer_instance()
        if type(primary_loadbalancer) in types.StringTypes:
            return primary_loadbalancer
        assert(type(primary_loadbalancer) == Instance)
        return primary_loadbalancer.public_ip
        
    def get_all_instances(self):
        """ Get all information about all instances encoded as a JSON
        string. """
        data = {"loadbalancer": [elem.get_data() for elem in self.loadbalancer_instances],
                "webmachine": [elem.get_data() for elem in self.webmachine_instances],
                "riak": [elem.get_data() for elem in self.riak_instances]}
        return json.dumps(data)

class Instance(object):
    """ Wrapper around a cloud instance. """
    def __init__(self,
                 type,
                 public_dns,
                 public_ip,
                 private_ip,
                 id,
                 operational_state=None,
                 activation_state=None,
                 tags=None):
        self.type = type
        self.public_dns = public_dns
        self.public_ip = public_ip
        self.private_ip = private_ip
        self.id = id
        self.operational_state = operational_state
        self.activation_state = activation_state        
        self.tags = tags
        
    def get_data(self):
        """ Return as a JSON string. """
        data = {"type": self.type,
                "public_dns": self.public_dns,
                "public_ip": self.public_ip,
                "private_ip": self.private_ip,
                "id": self.id,
                "operational_state": self.operational_state,
                "activation_state": self.activation_state,
                "tags": self.tags}
        return data
        
    def __repr__(self):
        return str(self)
        
    def __str__(self):
        output = "Instance.\n"
        output += "\tType: %s\n" % (self.type, )
        output += "\tPublic DNS: %s\n" % (self.public_dns, )
        output += "\tPublic IP: %s\n" % (self.public_ip, )
        output += "\tPrivate IP: %s\n" % (self.private_ip, )
        output += "\tID: %s\n" % (self.id, )
        output += "\tOperational state: %s\n" % (self.operational_state, )
        output += "\tActivation state: %s\n" % (self.activation_state, )        
        output += "\tTags: %s\n" % (pprint.pformat(self.tags), )
        return output
# ----------------------------------------------------------------------

class DataPage(Resource):
    isLeaf = True
    def __init__(self):
        self.data = None
        self.data_lock = threading.Lock()
        self.default_interval = 60
        self.start_data_collection()        
        Resource.__init__(self)        
    
    def get_data(self):
        """ Get all of the information required to answer client
        requests about the state of the canvas service.  This is the
        heart of the class, and its sole purpose is to create
        a DataState instance.
        
        Although currently only polls Amazon Web Services could
        be extended to poll other cloud providers."""
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
                        operational_state = instance.tags.get("operational_state", "unknown")
                        container.append(Instance(type="aws",
                                                  public_dns=instance.public_dns_name,
                                                  public_ip=instance.ip_address,
                                                  private_ip=instance.private_ip_address,
                                                  id=instance.id,
                                                  activation_state=instance.state,
                                                  operational_state=operational_state,
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
        error_occurred = False
        with self.data_lock:
            if self.data is None:
                logger.error("self.data is None.  Probably not initialised yet.")
                result = "ERROR DataPage render_GET: self.data is None.  Probably not initialised yet."
                request.setResponseCode(500)
                error_occurred = True
            elif query not in self.data.AVAILABLE_FUNCTIONS:                                            
                logger.error("Could not find function for: '%s'." % (query, ))
                result = "ERROR DataPage render_GET: Could not find function for: '%s'" % (query, )
                request.setResponseCode(500)
                error_occurred = True
            else:
                function_member = getattr(self.data, query)
                result = function_member()
        if error_occurred:
            logger.error("result: %s" % (result, ))        
        else:
            logger.debug("result: %s" % (result, ))                
        return "%s" % (str(result), )

if __name__ == "__main__":
    root = Resource()
    root.putChild("data", DataPage())
    factory = Site(root)
    reactor.listenTCP(8880, factory)
    logger.info("running")
    reactor.run()
