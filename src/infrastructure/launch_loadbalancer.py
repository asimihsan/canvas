# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/infrastructure/launch_loadbalancer.py
#
# Use this file on your personal PC to set up and launch a load
# balancer instance.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Constants to change.
# ----------------------------------------------------------------------

# This is the AMI ID for the AMI you created at the end of Part 2,
# which has Erlang, Python, and HAProxy installed on it.
BASE_AMI_ID = "ami-21e4d355"

# What your keypair name is, again from Part 2.
KEY_NAME = "ai_keypair"

# This is the IP address of your personal machine.  We use this
# to only allow SSH access to your personal machine.  Get it from
# http://whatismyipaddress.com/
PERSONAL_IP_ADDRESS = "2.25.200.198"
# ----------------------------------------------------------------------

import os
import sys
import time
from boto.ec2.connection import EC2Connection
from string import Template

# ----------------------------------------------------------------------
# Constants to leave alone.
# ----------------------------------------------------------------------

# User data, if prefixed by the bash she bang, will be executed
# on startup.
USER_DATA = \
"""#!/bin/bash
rm -rf /home/ubuntu/canvas
git clone git://github.com/asimihsan/canvas.git /home/ubuntu/canvas
cd /home/ubuntu/canvas
git checkout part3
sudo chown -R ubuntu:ubuntu /home/ubuntu/canvas
"""

# ----------------------------------------------------------------------


    
import logging
logger = logging.getLogger('launch_loadbalancer')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger('launch_loadbalancer')

def tear_down_running_state(connection):
    """ Stop all running instances, remove all elastic IPs.
    """
    # ------------------------------------------------------------------
    # Terminate all running instances of everything.
    # ------------------------------------------------------------------
    logger.warning("About to terminate all running instances.  CTRL-C to abort!")
    time.sleep(5)
    for reservation in connection.get_all_instances():
        for instance in reservation.instances:
            if instance.state == "running":
                logger.warning("Terminating instance ID: '%s'" % (instance.id, ))
                instance.terminate()
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Remove all existing elastic IPs, get a new one, assign it
    # to the load balancer instance.
    # ------------------------------------------------------------------
    logger.warning("Remove all existing elastic IP allocations.")
    for address in connection.get_all_addresses():
        logger.warning("Removing elastic IP: '%s'" % (address.public_ip, ))
        address.disassociate()
        address.delete()
    # ------------------------------------------------------------------    

if __name__ == "__main__":
    logger.info("starting.")
    
    # ------------------------------------------------------------------
    # Validate the system environment.
    # ------------------------------------------------------------------
    for required_variable in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ACCOUNT_ID"]:
        if required_variable not in os.environ:
            logger.error("Require %s as system environment variable.  Please see Part 2." % (required_variable, ))
            sys.exit(1)        
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Get a connection to the EU region.
    # ------------------------------------------------------------------
    logger.debug("Get connection to the EU region...")
    conn = EC2Connection()
    region_eu = [region for region in conn.get_all_regions() if "eu-west" in region.name][0]
    conn_eu = region_eu.connect()
    # ------------------------------------------------------------------
    
    # -----------------------------------------------------------------    
    # Stop all running instances, delete all elastic IPs.
    # ------------------------------------------------------------------
    tear_down_running_state(conn_eu)
    if "--only_delete" in sys.argv:
        sys.exit(2)
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Set up all the security groups.  How horrid, because internally
    # all the security groups exist in a full-mesh of permissions
    # and the individual links need to be revoked before the
    # security groups can be deleted.
    # ------------------------------------------------------------------    
    logger.debug("Delete existing security groups...")
    existing_sgs = dict([(sg.name, sg) for sg in conn_eu.get_all_security_groups()])
    sg_loadbalancer = [value for (key, value) in existing_sgs.items() if key == u"loadbalancer"]
    sg_webmachine = [value for (key, value) in existing_sgs.items() if key == u"webmachine"]
    sg_riak = [value for (key, value) in existing_sgs.items() if key == u"riak"]    
    if len(sg_loadbalancer) != 0:
        if len(sg_webmachine) != 0:
            sg_loadbalancer[0].revoke(src_group=sg_webmachine[0])
        if len(sg_riak) != 0:
            sg_loadbalancer[0].revoke(src_group=sg_riak[0])
    if len(sg_webmachine) != 0:  
        if len(sg_loadbalancer) != 0:
            sg_webmachine[0].revoke(src_group=sg_loadbalancer[0])
        if len(sg_riak) != 0:
            sg_webmachine[0].revoke(src_group=sg_riak[0])
    if len(sg_riak) != 0:    
        if len(sg_loadbalancer) != 0:
            sg_riak[0].revoke(src_group=sg_loadbalancer[0])
        if len(sg_webmachine) != 0:
            sg_riak[0].revoke(src_group=sg_webmachine[0])        
    if len(sg_loadbalancer) != 0:
        conn_eu.delete_security_group("loadbalancer")
    if len(sg_webmachine) != 0:
        conn_eu.delete_security_group("webmachine")
    if len(sg_riak) != 0:
        conn_eu.delete_security_group("riak")        
    
    logger.debug("Create new security groups...")            
    sg_loadbalancer = conn_eu.create_security_group("loadbalancer", "Load Balancer Group")
    sg_riak = conn_eu.create_security_group("riak", "Riak Group")
    sg_webmachine = conn_eu.create_security_group("webmachine", "Webmachine Group")
    
    sg_loadbalancer.authorize("tcp", 22, 22, "%s/32" % (PERSONAL_IP_ADDRESS, ))    
    sg_riak.authorize("tcp", 22, 22, "%s/32" % (PERSONAL_IP_ADDRESS, ))
    sg_webmachine.authorize("tcp", 22, 22, "%s/32" % (PERSONAL_IP_ADDRESS, ))    
    
    sg_loadbalancer.authorize("tcp", 80, 80, "0.0.0.0/0")
    sg_loadbalancer.authorize("tcp", 443, 443, "0.0.0.0/0")    
    sg_loadbalancer.authorize(src_group=sg_webmachine)
    sg_webmachine.authorize(src_group=sg_loadbalancer)    
    sg_riak.authorize(src_group=sg_loadbalancer)
    sg_riak.authorize(src_group=sg_webmachine)
    sg_riak.authorize(src_group=sg_riak)    
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Launch a new EC2 instance based on the load balancer AMI from
    # Part 2.
    # ------------------------------------------------------------------
    logger.debug("Launching EC2 instance with AMI ID: '%s'" %  (BASE_AMI_ID, ))
    image_loadbalancer = conn_eu.get_image(BASE_AMI_ID)
    reservation = image_loadbalancer.run(key_name=KEY_NAME,
                                         security_groups=[sg_loadbalancer],
                                         instance_type="t1.micro",
                                         user_data=USER_DATA)
    instance = reservation.instances[0]
    while 1:
        time.sleep(3)
        instance.update()
        if instance.state != "pending":
            break
    logger.info("Load balancer instance now running with ID '%s' and public DNS name:\n%s" % (instance.id, instance.public_dns_name, ))    
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Remove all existing elastic IPs, get a new one, assign it
    # to the load balancer instance.
    # ------------------------------------------------------------------
    logger.debug("Getting a new elastic IP")
    conn_eu.allocate_address()
    address = conn_eu.get_all_addresses()[0]
    logger.info("Associating elastic IP '%s' to instance ID '%s'" % (address.public_ip, instance.id))
    address.associate(instance.id)
    # ------------------------------------------------------------------
    
    logger.info("exiting successfully.")