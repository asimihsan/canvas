#!/usr/local/bin/python

# ---------------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see the accompanying
# file license.txt or http://www.opensource.org/licenses/mit-license.php.
# ---------------------------------------------------------------------------

# ----------------------------------------------------------------------
#   Run regularly in order to update haproxy.conf with the latest
#   known set of webmachine / riak / etc. nodes and hot-configure
#   any running haproxy nodes.
# ----------------------------------------------------------------------

import os
import sys
import re
from string import Template
from boto.ec2.connection import EC2Connection
import operator

# ----------------------------------------------------------------------
#   Constants.
# ----------------------------------------------------------------------
APP_NAME = "cron_update_haproxy_conf"
CANVAS_ROOT = "/home/ubuntu/canvas/"
LOG_PATH = os.path.join(CANVAS_ROOT, "log")
HAPROXY_CONF = os.path.join(CANVAS_ROOT, "src", "loadbalancer", "haproxy.conf")
HAPROXY_CMD = "service haproxyd restart"

RE_WEBMACHINE_START = re.compile("# !-- start: webmachine instances --!")
RE_WEBMACHINE_END = re.compile("# !-- end: webmachine instances --!")
RE_RIAK_START = re.compile("# !-- start: riak instances --!")
RE_RIAK_END = re.compile("# !-- end: riak instances --!")

AWS_REGION = "eu-west"
AWS_WEBMACHINE_GROUP_NAME = "webmachine"
AWS_RIAK_GROUP_NAME = "riak"

HAPROXY_CONF_WEBMACHINE_TEMPL = Template("  server Webmachine${num} ${ip}:${port} check addr ${ip} port ${port}\n")
HAPROXY_CONF_RIAK_TEMPL = Template("  server Riak${num} ${ip}:${pb_port} check addr ${ip} port ${http_port}\n")
# ----------------------------------------------------------------------

import logging
import logging.handlers
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

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
    if not os.path.isfile(HAPROXY_CONF):
        logger.error("HAPROXY_CONF is not a file: '%s'" % (HAPROXY_CONF, ))
        sys.exit(2)
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    #   Read in haproxy.conf, validate it.
    # ------------------------------------------------------------------
    logger.debug("reading HAPROXY_CONF: '%s'" % (HAPROXY_CONF, ))    
    with open(HAPROXY_CONF) as f:
        contents = f.readlines()            
    webmachine_start = None
    webmachine_end = None
    riak_start = None
    riak_end = None
    for (i, line) in enumerate(contents):        
        if not webmachine_start:
            m = RE_WEBMACHINE_START.search(line)
            if m:
                webmachine_start = i
        if not webmachine_end:
            m = RE_WEBMACHINE_END.search(line)
            if m:
                webmachine_end = i
        if not riak_start:
            m = RE_RIAK_START.search(line)
            if m:
                riak_start = i
        if not riak_end:
            m = RE_RIAK_END.search(line)
            if m:
                riak_end = i
    if not webmachine_start:
        logger.error("Could not find RE_WEBMACHINE_START in HAPROXY_CONF.")
        sys.exit(3)
    if not webmachine_end:
        logger.error("Could not find RE_WEBMACHINE_END in HAPROXY_CONF.")
        sys.exit(4)
    if not riak_start:
        logger.error("Could not find RE_RIAK_START in HAPROXY_CONF.")
        sys.exit(5)
    if not riak_end:
        logger.error("Could not find RE_RIAK_END in HAPROXY_CONF.")
        sys.exit(6)                        
    # ------------------------------------------------------------------    
    
    # ------------------------------------------------------------------
    #   Get a list of all instances using security groups that
    #   indicate they're either webmachine or riak instances.    
    # ------------------------------------------------------------------    
    logger.debug("Establishing AWS EC2 boto connection...")
    try:
        conn = EC2Connection()
    except:
        logger.exception("Unhandled exception.")
        raise
    logger.debug("Established AWS EC2 boto connection.")
    all_connections = [region.connect() for region in conn.get_all_regions()]
    all_reservations = [reservation for connection in all_connections                          
                                    for reservation in connection.get_all_instances()]    
    webmachine_instances = []
    riak_instances = []
    for reservation in all_reservations:
        logger.debug("Considering reservation: '%s'" % (reservation, ))
        if any(group.id == AWS_WEBMACHINE_GROUP_NAME for group in reservation.groups):
            logger.debug("Reservation '%s' has AWS_WEBMACHINE_GROUP_NAME" % (reservation, ))
            for instance in reservation.instances:
                if instance.state == "running":
                    logger.debug("Instance '%s' of webmachine is running." % (instance, ))
                    webmachine_instances.append(instance)
        elif any(group.id == AWS_RIAK_GROUP_NAME for group in reservation.groups):
            logger.debug("Reservation '%s' has AWS_RIAK_GROUP_NAME" % (reservation, ))
            for instance in reservation.instances:
                if instance.state == "running":
                    logger.debug("Instance '%s' of riak is running." % (instance, ))
                    riak_instances.append(instance)
    # ------------------------------------------------------------------                        
                    
    # ------------------------------------------------------------------    
    #   Refresh haproxy.conf.
    # ------------------------------------------------------------------    
    webmachine_lines = []
    riak_lines = []
    if len(webmachine_instances) != 0:
        webmachine_instances.sort(key=operator.attrgetter("private_ip_address"))
        for (i, instance) in enumerate(webmachine_instances, start=1):
            logger.debug("Inserting webmachine instance: '%s'" % (instance, ))
            if not "WEBMACHINE_PORT" in instance.tags:
                logger.error("Webmachine instance is missing 'WEBMACHINE_PORT' tag.  Skip")
                continue
            assert("WEBMACHINE_PORT" in instance.tags)
            ip = instance.private_ip_address
            port = instance.tags["WEBMACHINE_PORT"]
            line = HAPROXY_CONF_WEBMACHINE_TEMPL.substitute(num=i, ip=ip, port=port)
            logger.debug("Line is: %s" % (line.strip(), ))
            webmachine_lines.append(line)
    if len(riak_instances) != 0:
        riak_instances.sort(key=operator.attrgetter("private_ip_address"))
        for (i, instance) in enumerate(riak_instances, start=1):
            logger.debug("Inserting riak instance: '%s'" % (instance, ))
            if not "RIAK_PB_PORT" in instance.tag:
                logger.error("Riak instance is missing 'RIAK_PB_PORT' tag.  Skip")
                continue            
            if not "RIAK_HTTP_PORT" in instance.tag:
                logger.error("Riak instance is missing 'RIAK_HTTP_PORT' tag.  Skip")
                continue                            
            assert("RIAK_PB_PORT" in instance.tags)
            assert("RIAK_HTTP_PORT" in instance.tags)            
            ip = instance.private_ip_address
            pb_port = instance.tags["RIAK_PB_PORT"]
            http_port = instance.tags["RIAK_HTTP_PORT"]
            line = HAPROXY_CONF_RIAK_TEMPL.substitute(num=i, ip=ip, pb_port=pb_port, http_port=http_port)
            logger.debug("Line is: %s" % (line.strip(), ))
            riak_lines.append(line)    

    logger.debug("reading HAPROXY_CONF: '%s'" % (HAPROXY_CONF, ))    
    with open(HAPROXY_CONF) as f:
        contents = f.readlines()         
    old_contents = contents[:]
    for (i, line) in enumerate(contents[:-1]):        
        if RE_WEBMACHINE_START.search(line):
            while not RE_WEBMACHINE_END.search(contents[i+1]):
                contents.pop(i+1)
            for webmachine_line in webmachine_lines:
                contents.insert(i+1, webmachine_line)
    for (i, line) in enumerate(contents[:-1]):        
        if RE_RIAK_START.search(line):
            while not RE_RIAK_END.search(contents[i+1]):
                contents.pop(i+1)
            for riak_line in riak_lines:
                contents.insert(i+1, riak_line)        
    if ''.join(contents) != ''.join(old_contents):
        logger.debug("Contents have changed, so writing HAPROXY_CONF.")
        with open(HAPROXY_CONF, "w") as f:
            f.writelines(contents)
        logger.debug("Hot reconfigure haproxy")
        os.system(HAPROXY_CMD)
    else:
        logger.debug("Contents have not changed, leave HAPROXY_CONF untouched.")    
    # ------------------------------------------------------------------    
    
    logger.info("exiting successfully.")
    