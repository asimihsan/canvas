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
import datetime
import re
import operator

# ----------------------------------------------------------------------
# Constants to leave alone.
# ----------------------------------------------------------------------

# What port number to start using for Webmachine instances
STARTING_WEBMACHINE_PORT = 8000

# User data, if prefixed by the bash she bang, will be executed
# on startup.
USER_DATA = \
Template("""#!/bin/bash

. /home/ubuntu/.bash_profile
pip install -U httplib2 boto
sudo apt-get update
yes yes | sudo apt-get upgrade

rm -rf /home/ubuntu/canvas
git clone git://github.com/asimihsan/canvas.git /home/ubuntu/canvas
cd /home/ubuntu/canvas
git checkout part3
sudo chown -R ubuntu:ubuntu /home/ubuntu/canvas

/usr/local/bin/python /home/ubuntu/canvas/src/infrastructure/ec2tag_to_environment.py
""")

# What region to use.
REGION_NAME = "eu-west-1"

# Regular expression for a datetime string
re1='.*?'	# Non-greedy match on filler
re2='(webmachine)'	# Word 1
re3='.*?'	# Non-greedy match on filler
re4='(?P<year>\\d+)'	# Integer Number 1
re5='(_)'	# Any Single Character 1
re6='(?P<month>\\d+)'	# Integer Number 2
re7='(_)'	# Any Single Character 2
re8='(?P<day>\\d+)'	# Integer Number 3
re9='(T)'	# Any Single Word Character (Not Whitespace) 1
re10='(?P<hour>\\d+)'	# Integer Number 4
re11='(_)'	# Any Single Character 3
re12='(?P<minute>\\d+)'	# Integer Number 5
re13='(_)'	# Any Single Character 4
re14='(?P<second>\\d+)'	# Integer Number 6
RE_DATETIME = re.compile(''.join([re1,re2,re3,re4,re5,re6,re7,re8,re9,re10,re11,re12,re13,re14]), re.IGNORECASE|re.DOTALL)

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
    logger.debug("Get connection to the %s region..." % (REGION_NAME, ))
    conn_root = EC2Connection()
    region = [region for region in conn_root.get_all_regions() if REGION_NAME in region.name][0]
    conn = region.connect()
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Get the AMI ID for the more recent Webmachine image.
    # ------------------------------------------------------------------
    logger.debug("Finding latest Webmachine AMI ID...")
    all_images = conn.get_all_images()
    logger.debug("There are %s image(s) in total." % (len(all_images), ))
    my_images = [image for image in all_images if image.owner_id == os.environ["AWS_ACCOUNT_ID"]]
    logger.debug("There are %s image(s) that belong to me." % (len(my_images), ))
    webmachine_images = [image for image in my_images if "Base webmachine" in image.name]
    logger.debug("There are %s webmachine image(s)." % (len(webmachine_images), ))
    
    images_and_dates = []
    for image in webmachine_images:
        datetime_re_obj = RE_DATETIME.search(image.name)
        if not datetime_re_obj:
            logger.error("AMI ID '%s' with name '%s'.  Could not parse datetime from name.  Skip" % (image.id, image.name))
            continue
        assert(datetime_re_obj)
        datetime_obj = datetime.datetime(year=int(datetime_re_obj.groupdict()["year"]),
                                         month=int(datetime_re_obj.groupdict()["month"]),
                                         day=int(datetime_re_obj.groupdict()["day"]),
                                         hour=int(datetime_re_obj.groupdict()["hour"]),
                                         minute=int(datetime_re_obj.groupdict()["minute"]),
                                         second=int(datetime_re_obj.groupdict()["second"]))
        images_and_dates.append((image, datetime_obj))
    images_and_dates.sort(key=operator.itemgetter(1), reverse=True)
    image_webmachine = images_and_dates[0][0]
    logger.info("Will use Webmachine AMI ID '%s', name '%s'" % (image_webmachine.id, image_webmachine.name))
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Launch a new EC2 instance.
    # ------------------------------------------------------------------
    logger.info("Launching EC2 instance with AMI ID: '%s'" %  (image_webmachine.id, ))
    existing_sgs = dict([(sg.name, sg) for sg in conn.get_all_security_groups()])
    if "webmachine" not in existing_sgs:
        logger.error("Could not find security group called 'webmachine'")
        sys.exit(2)        
    sg_webmachine = [value for (key, value) in existing_sgs.items() if key == u"webmachine"][0]
    
    # Take the total number of Webmachine instances currently around,
    # running or not, and assume they're still using up ports.  Take
    # the next free port.
    taken_webmachine_ports = [STARTING_WEBMACHINE_PORT-1]
    all_reservations = conn.get_all_instances()
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