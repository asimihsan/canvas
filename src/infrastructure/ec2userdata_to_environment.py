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
import httplib2

# ----------------------------------------------------------------------
#   Constants.
# ----------------------------------------------------------------------
APP_NAME = 'ec2userdata_to_environment'
CANVAS_ROOT = "/home/ubuntu/canvas/"
LOG_PATH = os.path.join(CANVAS_ROOT, "log")

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

if __name__ == "__main__":
    logger.info("starting")
    
    # ------------------------------------------------------------------
    #   Validation.
    # ------------------------------------------------------------------
    if not os.path.isdir(CANVAS_ROOT):
        logger.error("CANVAS_ROOT is not a directory: '%s'" % (CANVAS_ROOT, ))
        sys.exit(1)    
        
    

logger = logging.getLogger(APP_NAME)

