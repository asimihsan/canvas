# ----------------------------------------------------------------------
# Copyright (c) 2011 Asim Ihsan (asim dot ihsan at gmail dot com)
# Distributed under the MIT/X11 software license, see 
# http://www.opensource.org/licenses/mit-license.php.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# File: canvas/src/infrastructure/put_external_ip_into_security_groups.py
#
# Use this file on your personal PC to adjust all security groups in
# all regions to use your personal machine's IP address for any
# SSH sections in such security groups.
# ----------------------------------------------------------------------

import os
import sys
import httplib2
import pprint
import re
from boto.ec2.connection import EC2Connection

import logging
logger = logging.getLogger('put_external_ip_into_security_groups')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger = logging.getLogger('put_external_ip_into_security_groups')

# ----------------------------------------------------------------------
# Constants to leave alone.
# ----------------------------------------------------------------------

# Regular expressions
re1='.*?'	# Non-greedy match on filler
re2="Your computer's IP address is:"
re3='.*?'
re4='(?P<ip_address>((?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))(?![\\d]))'	# IPv4 IP Address 1
RE_MYIPADDRESS = re.compile(''.join([re1,re2,re3,re4]),re.IGNORECASE|re.DOTALL)

re1='.*?'	# Non-greedy match on filler
re2="Your IP address is"
re3='.*?'
re4='(?P<ip_address>((?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))(?![\\d]))'	# IPv4 IP Address 1
RE_NEFSC_NOAA = re.compile(''.join([re1,re2,re3,re4]),re.IGNORECASE|re.DOTALL)

re1='(?P<ip_address>((?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))(?![\\d]))'
RE_IP = re.compile(re1, re.IGNORECASE|re.DOTALL)

# ----------------------------------------------------------------------

def get_ip_from_nefsc_noaa():
    """ Use http://ip.nefsc.noaa.gov/ to get my external IP address. """
    h = httplib2.Http()
    url = "http://ip.nefsc.noaa.gov/"
    resp, content = h.request(url)
    if resp.status != 200:
        logger.error("get_ip_from_nefsc_noaa() returns non-200 status code.  Failed.")
        logger.error(pprint.pformat(resp))
        return None
    m = RE_NEFSC_NOAA.search(content)
    if not m:
        logger.error("get_ip_from_nefsc_noaa(): Couldn't find IP address.")
        return None    
    return m.groupdict()["ip_address"]    

def get_ip_from_icanhazip():
    """ Use icanhazip.com to get my external IP address. """
    h = httplib2.Http()    
    url = "http://icanhazip.com/"
    resp, content = h.request(url)    
    if resp.status != 200:
        logger.error("get_ip_from_icanhazip() returns non-200 status code.  Failed.")
        logger.error(pprint.pformat(resp))
        return None
    if not RE_IP.match(content.strip()):
        logger.error("get_ip_from_icanhazip(): Result isn't an IP address: %s" % (content.strip(), ))
        return None
    return content.strip()
    
def get_ip_from_myipaddress():
    """ Use www.myipaddress.com to get my external IP address."""
    h = httplib2.Http()
    h.follow_redirects = False
    url = "http://www.myipaddress.com/"
    resp, content = h.request(url)   
    if resp.status != 302:
        logger.error("get_ip_from_myipaddress(): Did not redirect, not expected.")
        return None
    url = resp['location']
    cookie = resp['set-cookie']
    headers = {"Cookie": cookie}
    logger.debug("get_ip_from_myipaddress(): Re-fetching URL %s with cookie %s" % (url, cookie))
    resp, content = h.request(url, headers=headers) 
    if resp.status != 200:
        logger.error("get_ip_from_myipaddress(): Did not get status code 200 after redirect.")
        return None
    m = RE_MYIPADDRESS.search(content)
    if not m:
        logger.error("get_ip_from_myipaddress(): Could not find IP address in output.")
        return None
    return m.groupdict()["ip_address"]      
    
def put_external_ip_into_security_groups(ssh_from_port = 22,
                                         ssh_to_port = 22,
                                         leave_existing_rules = False,
                                         logger = logger):
    """ Put the external IP address of this machine into all security
    groups in all regions as an SSH rule. """
    
    logger.info("put_external_ip_into_security_groups() entry.  ssh_from_port: %s, ssh_to_port: %s, leave_existing_rules: %s" % (ssh_from_port, ssh_to_port, leave_existing_rules))
                                         
    # ------------------------------------------------------------------
    # Get a connection to all regions.
    # ------------------------------------------------------------------
    logger.debug("Get connections to all regions...")
    conn_root = EC2Connection()
    conns = [region.connect() for region in conn_root.get_all_regions()]    
    # ------------------------------------------------------------------    

    # ------------------------------------------------------------------
    #   Get my external IP address using a web service.  Keep trying
    #   until an external IP source returns an IP address.
    # ------------------------------------------------------------------
    external_ip = None
    for possible_source in [get_ip_from_icanhazip,
                            get_ip_from_nefsc_noaa,                            
                            get_ip_from_myipaddress]:
        logger.debug("Attempting to use source: %s" % (possible_source, ))
        external_ip = possible_source()
        if external_ip is not None:
            logger.info("Found external IP address as: %s" % (external_ip, ))    
            break
    if not external_ip:
        logger.error("Could not determine external IP address.")
        sys.exit(1)
    
    # ------------------------------------------------------------------
    #   Fix all security groups that mention SSH connections to a
    #   single IP address.
    # ------------------------------------------------------------------
    for conn in conns:
        logger.debug("considering connection: %s" % (conn, ))
        for sg in conn.get_all_security_groups():    
            logger.debug("considering security group: %s" % (sg, ))
            if not leave_existing_rules:
                logger.debug("Look for existing SSH rules to delete.")
                for rule in sg.rules:
                    #logger.debug("considering rule: %s" % (rule, ))
                    if ((rule.ip_protocol == "tcp") and
                        (rule.from_port == str(ssh_from_port)) and
                        (rule.to_port == str(ssh_to_port))):
                        logger.debug("SSH rule found.  grants: %s" % (pprint.pformat(rule.grants), ))
                        if len(rule.grants) == 0:
                            logger.error("SSH rule has no IP addresses.  Ignore it.")
                            continue
                        assert(len(rule.grants) >= 1)                                                
                        logger.info("Removing SSH rule. From port: %s, to port: %s, IP: %s" % (rule.from_port, rule.to_port, rule.grants[0].cidr_ip))
                        rc = conn.revoke_security_group(group_name = sg.name,
                                                        ip_protocol = rule.ip_protocol,
                                                        from_port = int(rule.from_port),
                                                        to_port = int(rule.to_port),
                                                        cidr_ip = rule.grants[0].cidr_ip)
                        logger.debug("revoke_security_group() returns: %s" % (rc, )) 
            logger.info("Adding SSH rule. From port: %s, to port: %s, IP: %s" % (ssh_from_port, ssh_to_port, external_ip))
            rc = conn.authorize_security_group(group_name = sg.name,
                                               ip_protocol = "tcp",
                                               from_port = int(ssh_from_port),
                                               to_port = int(ssh_to_port),
                                               cidr_ip = "%s/32" % (external_ip, ))
            logger.debug("authorize_security_group() returns: %s" % (rc, ))                    
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
    # Process command-line arguments.
    # ------------------------------------------------------------------
    leave_existing_rules = "--leave_existing_rules" in sys.argv[1:]
    # ------------------------------------------------------------------
    
    put_external_ip_into_security_groups(leave_existing_rules = leave_existing_rules)
    
    logger.info("Exiting successfully.")

