# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/infrastructure/sniff.py
#
# Use this file on your personal PC or on an Amazon EC2 instance to
# get a quick diagnostic of the state of your web service.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
#   Imports.
# ----------------------------------------------------------------------
from __future__ import with_statement
import os
import sys
import logging
import collections

from boto.ec2.connection import EC2Connection
from fabric.api import *
from fabric.contrib.console import confirm
import fabric.network
import colorama
from colorama import Fore, Back, Style

# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
#   Logging.
# ----------------------------------------------------------------------
APP_NAME = 'sniff'
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger(APP_NAME)
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
#   Constants to change.
# ----------------------------------------------------------------------
KEY_FILENAME = r"C:\Users\ai\Documents\AWS\keys\ai_keypair"
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
#   Constants to leave alone.
# ----------------------------------------------------------------------
AWS_LOADBALANCER_GROUP_NAME = "loadbalancer"
AWS_WEBMACHINE_GROUP_NAME = "webmachine"
AWS_RIAK_GROUP_NAME = "riak"

REMOTE_USERNAME = "ubuntu"
# ----------------------------------------------------------------------

def validate_local_environment():
    for required_variable in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ACCOUNT_ID"]:
        if required_variable not in os.environ:
            logger.error("Require %s as system environment variable." % (required_variable, ))
            return False
    return True
    
def get_aws_connections():
    logger = logging.getLogger("%s.get_aws_connections" % (APP_NAME, ))
    logger.debug("entry.")
    conn_root = EC2Connection()
    conns = [region.connect() for region in conn_root.get_all_regions()]    
    return conns
    
Instances = collections.namedtuple("Instances", [AWS_LOADBALANCER_GROUP_NAME, AWS_WEBMACHINE_GROUP_NAME,AWS_RIAK_GROUP_NAME])
def get_instances_from_conns(all_connections):
    logger = logging.getLogger("%s.get_instances_from_conns" % (APP_NAME, ))
    logger.debug("entry.")
    all_reservations = [reservation for connection in all_connections                          
                                    for reservation in connection.get_all_instances()]    
    loadbalancer_instances = []
    webmachine_instances = []
    riak_instances = []
    for reservation in all_reservations:
        logger.debug("considering reservation: %s" % (reservation, ))
        for (container, group_name) in [(loadbalancer_instances, AWS_LOADBALANCER_GROUP_NAME),
                                        (webmachine_instances, AWS_WEBMACHINE_GROUP_NAME),
                                        (riak_instances, AWS_RIAK_GROUP_NAME)]:
            if any(group.id == group_name for group in reservation.groups):
                logger.debug("reservation has %s group name." % (group_name, ))
                for instance in reservation.instances:
                    if instance.state == "running":
                        logger.debug("Instance '%s' of %s is running." % (instance, group_name))
                        container.extend(reservation.instances)
    results = Instances(loadbalancer_instances, webmachine_instances, riak_instances)
    return results
    
def validate_loadbalancer_instance(instance):
    logger = logging.getLogger("%s.validate_loadbalancer_instance" % (APP_NAME, ))
    logger.debug("entry. instance: %s. DNS: %s" % (instance, instance.public_dns_name))
    run("sleep 5; ls ~")    
    run("ls -l /home/ubuntu/canvas/log")    
    
def main():
    logger.info("Starting main.")
    colorama.init()
    
    try:        
        # --------------------------------------------------------------
        #   Validate the environment.
        # --------------------------------------------------------------
        rc = validate_local_environment()
        if not rc:
            logger.error("Local environment failed validation.  See logs for details.")
            sys.exit(1)
        # --------------------------------------------------------------
        
        # --------------------------------------------------------------
        #   Get connections and all instances in all regions.
        # --------------------------------------------------------------    
        logger.info("Getting AWS connections...")
        conns = get_aws_connections()
        logger.info("Getting AWS instances...")
        instances = get_instances_from_conns(conns)
        # --------------------------------------------------------------
        
        # --------------------------------------------------------------
        #   Validate the function.  This means doing an HTTP GET on the
        #   elastic IP, and nothing more.  Finer-grained sniffing
        #   is performed by per-instance validation.
        # --------------------------------------------------------------
        
        # --------------------------------------------------------------
        
        # --------------------------------------------------------------
        #   Validate the instances.
        #
        #   host_string cannot be a unicode string or else the script
        #   fails on Windows, so we explicitly str() it.
        #
        #   Fabric is a bit finicky when using it as a library rather
        #   than executing scripts using 'fab'.  Hence a bit of
        #   boiler-plate to get it to connect to a particular host.
        # --------------------------------------------------------------
        for instance in instances.loadbalancer:
            with settings(host_string=str(instance.public_dns_name),
                          key_filename=KEY_FILENAME,
                          user=REMOTE_USERNAME):
                validate_loadbalancer_instance(instance)
        # --------------------------------------------------------------    
        
    finally:
        logger.info("Cleanup.")
        logger.debug("Disconnect all SSH sessions...")
        fabric.network.disconnect_all()
    
if __name__ == "__main__":
    main()


