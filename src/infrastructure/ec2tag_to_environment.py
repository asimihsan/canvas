# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/infrastructure/ec2userdata_to_environment.py
#
# Execute this file on EC2 instance startup, e.g. by putting it into
# /etc/rc.local, or by executing it using a user data bash script.
# It will take all tags assigned to the EC2 instance and put them
# into the ubuntu's user's bash_profile as environment variables.
# ----------------------------------------------------------------------

import os
import sys
from boto.ec2.connection import EC2Connection
from string import Template
import socket

# ----------------------------------------------------------------------
#   Constants.
# ----------------------------------------------------------------------
APP_NAME = 'ec2tag_to_environment'
HOME_FOLDER = "/home/ubuntu/"
CANVAS_ROOT = os.path.join(HOME_FOLDER, "canvas")
LOG_PATH = os.path.join(CANVAS_ROOT, "log")
BASH_PROFILE_FILE = os.path.join(HOME_FOLDER, ".bash_profile")

AWS_REGION = "eu-west-1"
# ----------------------------------------------------------------------

import logging
import logging.handlers
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger(APP_NAME)

if not os.path.isdir(LOG_PATH):
    os.makedirs(LOG_PATH)
fh = logging.handlers.RotatingFileHandler(os.path.join(LOG_PATH, '%s.log' % (APP_NAME, )), maxBytes=10000000, backupCount=5)
fh.setFormatter(formatter)
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

logger = logging.getLogger(APP_NAME)

if __name__ == "__main__":
    logger.info("starting")
    
    # ------------------------------------------------------------------
    #   Validation.
    # ------------------------------------------------------------------
    if not os.path.isdir(CANVAS_ROOT):
        logger.error("CANVAS_ROOT is not a directory: '%s'" % (CANVAS_ROOT, ))
        sys.exit(1)    
    if not os.path.isfile(BASH_PROFILE_FILE):
        logger.error("Bash profile file '%s' does not exist." % (BASH_PROFILE_FILE, ))
        sys.exit(1)
        
    # ------------------------------------------------------------------
    # Find the tags for this instance and pipe them into the 
    # /home/ubuntu/.bash_profile file as system environment variables.
    # ------------------------------------------------------------------
    with open(BASH_PROFILE_FILE) as f:
        lines = f.readlines()
    
    hostname = socket.getfqdn()
    logger.debug("My hostname is '%s'" % (hostname, ))
    conn_root = EC2Connection()
    all_connections = [region.connect() for region in conn_root.get_all_regions()]
    all_instances = [instance for connection in all_connections                          
                              for reservation in connection.get_all_instances()
                              for instance in reservation.instances]
    if not any(instance.private_dns_name == hostname for instance in all_instances):
        logger.error("Could not match my hostname with any running instance.")
        sys.exit(1)
    my_instance = [instance for instance in all_instances if instance.private_dns_name == hostname][0]
    logger.info("I am instance ID '%s', AMI ID '%s'" % (my_instance.id, my_instance.image_id))
    
    BASH_LINE = Template("export ${key}=${value}")
    for (key, value) in my_instance.tags.items():
        logger.debug("Setting key %s to value %s" % (key, value))
        lines.append(BASH_LINE.substitute(key=key, value=value))
        
    logger.info("Writing file: '%s'" % (BASH_PROFILE_FILE, ))
    with open(BASH_PROFILE_FILE, "w") as f:
        f.write(''.join(lines))
    
    logger.info("exiting successfully.")
