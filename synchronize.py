#!/usr/bin/env python

"""
Utilities for parsing basic text-based zonefiles.
"""

import re
import pyflare
import os
import argparse
import sys

def parse(buffer):
    """
    Parse a string into an enumeration of (name, type, target) tuples; for
    example:
    
      # a comment
      a CNAME example.com
      b A example.com
    
    results in:
      
      [
        ("a", "CNAME", "example.com"),
        ("b", "A", "example.com")
      ]
    """

    for line in buffer.split("\n"):
        line = line.split("#")[0].strip()
        if not line:
            continue

        subdomain, record_type, content = line.split(" ")

        validation = {
            r'^(CNAME|A)$': record_type,
            r'^(@|[a-zA-Z0-9]+)$': subdomain,
            r'^.+$': content
        }

        for pattern, value in validation.items():
            if not re.match(pattern, value):
                raise ValueError("in {line!r}, {value!r} must match {pattern!r}"
                    .format(**locals()))

        yield (subdomain, record_type, content)

def apply(zone_name, parsed_zone, cloudflare, live=True):
    """
    Applies DNS records in the format returned from +parse+ to a CloudFlare
    zone.
    """

    # Extract values currently in DNS.
    present = set()
    record_ids = {}
    for record in cloudflare.rec_load_all(zone_name):
        name = record["display_name"] if record["name"] != zone_name else "@"
        present.add((name, record["type"], record["content"]))
        record_ids[name] = record["rec_id"]

    # Compute steps needed to update the live zone file.
    future = set(parsed_zone)
    to_add = future - present
    to_remove = present - future

    # Remove outdated DNS records.
    for subdomain, record_type, content in to_remove:
        print("- {subdomain} {record_type} {content}".format(**locals()))
        
        if live:
            cloudflare.rec_delete(zone_name, record_ids[subdomain])

    # Add new DNS records.
    for subdomain, record_type, content in to_add:
        print("+ {subdomain} {record_type} {content}".format(**locals()))

        if live:
            cloudflare.rec_new(
                zone_name,
                record_type,
                subdomain,
                content,
                1, # ttl (1=automatic)
                None, # prio
                None, # service
                None, # service name
                None, # protocol
                None, # weight
                None, # port
                None  # target
            )

def main(argv):
    parser = argparse.ArgumentParser(description='Push Settings to CloudFlare.')
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="do everything but actually change DNS")
    parser.add_argument("zone_name", help="where to apply the settings")
    parser.add_argument("file_path", help="source of settings (default: stdin)")

    opts = parser.parse_args(argv)

    # Configure a CloudFlare API client.
    email, key = os.environ["CF_EMAIL"], os.environ["CF_KEY"]
    cloudflare = pyflare.PyflareClient(email, key)

    # Extract records from the zone file.
    try:
        records = parse(open(opts.file_path).read())
    except ValueError, e:
        print(str(e))
        return 1
    
    # Apply the changes to DNS.
    apply(opts.zone_name, records, cloudflare, live=(not opts.dry_run))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))