# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/infrastructure/launch_webmachine.py
#
# Use this file on your personal PC to set up and launch a Webmachine
# instance. This script assumes that you have already used
# launch_loadbalancer.py to start a load balancer instance.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Constants to change.
# ----------------------------------------------------------------------

# What your keypair name is, from Part 2.
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

# This is the public AMI ID for the AMI I created at the end of Part
# 2.  This is different from the AMI you used in launch_loadbalancer.py
# because this doesn't come with HAProxy, and is missing the secret
# credentials that go inside ~/.aws_keys.
BASE_AMI_ID = "ami-4fe7d03b"

# What port number to start using for Webmachine instances
STARTING_WEBMACHINE_PORT = 8000

# User data, if prefixed by the bash she bang, will be executed
# on startup.
#
# TODO export doesn't work.  Stash port somewhere readable from Erlang.
USER_DATA = \
Template("""#!/bin/bash
rm -rf /home/ubuntu/canvas
git clone git://github.com/asimihsan/canvas.git /home/ubuntu/canvas
cd /home/ubuntu/canvas
git checkout part3
sudo chown -R ubuntu:ubuntu /home/ubuntu/canvas

sudo export WEBMACHINE_PORT=${webmachine_port}
""")

# ----------------------------------------------------------------------
    
import logging
logger = logging.getLogger('launch_webmachine')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger('launch_webmachine')

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
    
    # ------------------------------------------------------------------
    # Launch a new EC2 instance based on the public AMI from Part 2.
    # ------------------------------------------------------------------
    logger.debug("Launching EC2 instance with AMI ID: '%s'" %  (BASE_AMI_ID, ))
    image_webmachine = conn_eu.get_image(BASE_AMI_ID)
    existing_sgs = dict([(sg.name, sg) for sg in conn_eu.get_all_security_groups()])
    if "webmachine" not in existing_sgs:
        logger.error("Could not find security group called 'webmachine'")
        sys.exit(2)        
    sg_webmachine = [value for (key, value) in existing_sgs.items() if key == u"webmachine"][0]
    
    # Take the total number of Webmachine instances currently around,
    # running or not, and assume they're still using up ports.  Take
    # the next free port.
    taken_webmachine_ports = [STARTING_WEBMACHINE_PORT-1]
    all_reservations = conn_eu.get_all_instances()
    for reservation in all_reservations:
        if any(group.id == "webmachine" for group in reservation.groups):
            for instance in reservation.instances:
                if "webmachine_port" not in instance.tags:
                    logger.warning("Tag 'webmachine_port' not found in instance ID %s marked as Webmachine instance." % (instance.id, ))
                    continue
                assert("webmachine_port" in instance.tags)
                taken_webmachine_ports.append(int(instance.tags["webmachine_port"]))
    webmachine_port = max(taken_webmachine_ports) + 1
    logger.debug("Will set WEBMACHINE_PORT tag to: '%s'" % (webmachine_port, ))
    user_data = USER_DATA.substitute(webmachine_port=webmachine_port)
    reservation = image_webmachine.run(key_name=KEY_NAME,
                                       security_groups=[sg_webmachine],
                                       instance_type="t1.micro",
                                       user_data=user_data)
    instance = reservation.instances[0]
    while 1:
        time.sleep(3)
        instance.update()
        if instance.state != "pending":
            break
    logger.info("Webmachine instance now running with ID '%s' and public DNS name:\n%s" % (instance.id, instance.public_dns_name, ))    
    instance.add_tag("webmachine_port", webmachine_port)
    # ------------------------------------------------------------------    

    logger.info("exiting successfully.")