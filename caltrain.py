#!/usr/bin/python
# -------------------------------------------------------------------------------
# caltrain.py
# Copyright (c) 2012 Marco Frigino
#
# Utility for finding caltrain schedule info, i.e. departure times for earliest
# route connections, or fastest route connections.
# Also can output caltrain schedules, station name lists and make coffee.
#
# 2012-05-09    Created
# 2014-04-29    Updated to match current Caltrain HTML
# -------------------------------------------------------------------------------

import json
import sys
import getopt
import pickle
import httplib, urllib
import xml.etree.ElementTree
import unicodedata
from datetime import datetime, timedelta
from textwrap import wrap
from math import radians, cos, sin, asin, sqrt

# -------------------------------------------------------------------------------
#   debug
# -------------------------------------------------------------------------------
# Switch to True to enable debug
def debug(s):
    if False:
        print s
    else:
        pass

# -------------------------------------------------------------------------------
# Cache
#
# Implements object pickling and unpickling via cache file
# -------------------------------------------------------------------------------
class Cache:

    # --------------------------------
    @staticmethod
    def get_file_objects(file_path):
        """ Opens cache file and returns list of objects """
        obj_list = []
        try:
            with open(file_path) as f:
                obj_list = pickle.load(f)
        except Exception:
            # Ignore, but should be logged in reality
            pass
        return obj_list

    # --------------------------------
    @staticmethod
    def put_file_objects(file_path, obj_list):
        """ Opens cache file and writes list of objects """
        try:
            with open(file_path, 'w') as f:
                pickle.dump(obj_list, f)
        except Exception:
            # Ignore, but should be logged in reality
            pass

# -------------------------------------------------------------------------------
# ScheduleParser
#
# Utility class for parsing caltrain HTML pages and building schedule and
# station objects. Subject to breakage if caltrain page changes.
# -------------------------------------------------------------------------------
class ScheduleParser(object):

    # --------------------------------
    def make_schedule(self, is_weekday, is_northbound):
        """ Scan caltrain schedule web page and return schedule
        object matching given text (northbound, southbound) """
        debug("ScheduleParser.make_schedule")

        # Build html search strings
        direction = "Northbound" if is_northbound else "Southbound"
        when = "weekday" if is_weekday else "weekend"
        summary = "Weekday" if is_weekday else "Weekend and Holiday"

        # Build table start search tag
        summary_tag = 'summary="%s %s service"' % (summary, direction)
        table_end_tag = '</table>'

        # Create new schedule to fill
        schedule = Schedule("%s %s Schedule" % (summary, direction))

        # Fetch desired caltrain schedule page
        err = None
        try:
            conn = httplib.HTTPConnection("www.caltrain.com")
            url = "/schedules/%stimetable.html" % when
            conn.request("GET", url)
            r = conn.getresponse()
            if r.status == 200:
                debug("Got schedule from: www.caltrain.com%s" % url)
                resp_html = r.read()
                if resp_html:
                    # search for schedule table in html
                    debug("Searching for schedule start match: %s" % summary_tag)
                    summary_start_idx = resp_html.find(summary_tag)
                    if summary_start_idx != -1:
                        # Found summary text, backtrack to table start
                        tbl_start_idx = resp_html.rfind('<table', 0, summary_start_idx)
                        if tbl_start_idx != -1:
                            debug("Found schedule start at char: %s" % tbl_start_idx)
                            debug("Searching for schedule end match: %s" % table_end_tag)
                            tbl_end_idx = resp_html.find(table_end_tag, tbl_start_idx)
                            if tbl_end_idx != -1:
                                debug("Found schedule end at char: %s" % tbl_end_idx)
                                # Parse between table start, end tags
                                self._parse_schedule_table(resp_html,
                                        tbl_start_idx, tbl_end_idx + len(table_end_tag),
                                        schedule)
                            else:
                                err = "Cant find table end:"
                        else:
                            err = "Cant find table start:"
                    else:
                        err = "Cant find table summary match:"
                else:
                    err = "Got blank schedule:"
            else:
                err = "Can't retrieve:"
        except Exception as e:
            err = "Exception retrieving schedule %s" % e
        if err:
            raise Usage(err + " " + schedule.name())
        return schedule

    # --------------------------------
    def _parse_schedule_table(self, html, start_idx, end_idx, schedule):
        """ Fill given schedule by parsing given table in html """
        debug("Parsing schedule table from chars %s to %s" % (start_idx, end_idx))

        # Add inline DTD to get around &nbsp; unknown chars
        dtd = '<?xml version="1.1" ?><!DOCTYPE naughtyxml [<!ENTITY nbsp "&#0160;">]>'
        table_html = html[start_idx:end_idx]
        # Parse retrieved html
        t = xml.etree.ElementTree.fromstring(dtd + table_html)
        debug("Table parsed.")
        # Look for each row
        table_rows = t.findall('tbody/tr/')
        for row in table_rows[1:]:
            debug("Parsing row: %s " % row)
            station_link = row.find('th/a')
            if station_link is not None:
                # Get station name. Check for weird unicode data
                station_name = station_link.text
                debug("Found station %s " % station_name)
                if isinstance(station_link.text, unicode):
                    station_name = unicodedata.normalize('NFKD',
                                    station_link.text).encode('ascii','ignore')
                # Got name, now get station times
                if station_name:
                    times = self._parse_station_times_from_row(row)
                    schedule.add_station_with_times(station_name, times)

    # --------------------------------
    def _parse_station_times_from_row(self, row):
        """ Return Time object list by parsing schedule table row """
        debug("Parsing station times...")
        times = []
        hours_to_add = 0
        morning = True
        # Parse all row columns
        cols = row.findall('td')
        for c in cols:
            tm = Time()
            # Try matching italic times (morning)
            time_text = self._find_element_tag_text(c, 'em')
            if time_text:
                # If flipped from PM to AM, add 24 hours
                if not morning:
                    morning = not morning
                    hours_to_add = 24
                tm.set(time_text, hours_to_add)
            else:
                # Try matching afternoon times (bold)
                time_text = self._find_element_tag_text(c, 'strong')
                if time_text:
                    # If flipped from AM to PM, add 12 hours
                    if morning:
                        morning = not morning
                        hours_to_add = 12
                    tm.set(time_text, hours_to_add)
            times.append(tm)
        return times

    # --------------------------------
    def _find_element_tag_text(self, elem, search_tag):
        """ Seek search tag in elem or sub-elements and return text value """
        found = elem.findall(search_tag)
        if found:
            return self._find_element_with_text(found[0])
        for e in elem:
            text = self._find_element_tag_text(e, search_tag)
            if text:
                return text
        return None

    # --------------------------------
    def _find_element_with_text(self, elem):
        """ Seek elem or sub-elements until text found """
        if elem.text:
            return elem.text
        for e in elem:
            text = self._find_element_with_text(e)
            if text:
                return text
        return None

# -------------------------------------------------------------------------------
# Time
#
# Represents schedule times. Uses datetime internally to handle calculations of
# departure and arrival differences that results in a day prior or day later.
# Invalid times print as --:--
# -------------------------------------------------------------------------------
class Time(object):

    # --------------------------------
    def __init__(self):
        """ Default constructor """
        self._time = None

    # --------------------------------
    def __str__(self):
        """ Return string representation as 24hr time or --:-- """
        return self._time.strftime("%H:%M") if self._time else "--:--"

    # --------------------------------
    def __eq__(self, other):
        """ True if time == another """
        return self._time.__eq__(other._time)

    # --------------------------------
    def __ne__(self, other):
        """ True if time != another """
        return self._time.__ne__(other._time)

    # --------------------------------
    def __lt__(self, other):
        """ True if time < another """
        return self._time.__lt__(other._time)

    # --------------------------------
    def __le__(self, other):
        """ True if time <= another """
        return self._time.__le__(other._time)

    # --------------------------------
    def __gt__(self, other):
        """ True if time > another """
        return self._time.__gt__(other._time)

    # --------------------------------
    def __ge__(self, other):
        """ True if time >= another """
        return self._time.__ge__(other._time)

    # --------------------------------
    def is_valid(self):
        """ Return true if this object has known time """
        return self._time is not None

    # --------------------------------
    def set(self, time_text, hours_to_add=0):
        """ Set time from expected hh:mm[AM|PM] text and adjust by hours to add """
        try:
            t = datetime.strptime(time_text, "%I:%M")
            if hours_to_add:
                t += timedelta(hours = hours_to_add)
            self._time = t
        except ValueError:
            self._time = None

    # --------------------------------
    def time_delta(self, other):
        """ Return timedelta obj difference with other time """
        return other._time - self._time

# -------------------------------------------------------------------------------
# Location
#
# Represents geocodable locations, such as cities, addresses, lat/lon, etc.
# Actual geocoding occurs only when coordinates are needed in the object.
# -------------------------------------------------------------------------------
class Location(object):

    # Class variables for caching addresses -> coordinates
    _geocode_cache = {}
    _geocode_cache_name = "caltrain_geocode_cache.txt"

    # --------------------------------
    def __init__(self, address=None, lat=None, lon=None, dont_cache=False):
        """ Default constructor """
        self._address = address
        self._dont_cache = dont_cache
        self.set_lat_lon(lat, lon)

    # --------------------------------
    def __str__(self):
        """ Returns string representation """
        return "%s (%s, %s)" % (self._address, self._lat, self._lon)

    # --------------------------------
    def is_geocoded(self):
        """ Returns True if location already geocoded """
        return (self._lat, self._lon) != (None, None)

    # --------------------------------
    def get_lat_lon(self):
        """ Returns lat, lon """
        if not self.is_geocoded():
            self.geocode()
        return self._lat, self._lon

    # --------------------------------
    def set_lat_lon(self, lat, lon):
        """ Sets lat, lon. If set to None, removes location from cache """
        self._lat, self._lon = lat, lon
        if (lat, lon) == (None, None):
            if self._address in Location._geocode_cache:
                del Location._geocode_cache[self._address]
        elif not self._dont_cache:
            Location._geocode_cache[self._address] = lat, lon

    # --------------------------------
    def distance_to(self, other):
        """ Return KM distance to other location """
        # Force geocoding on both locations
        self.get_lat_lon()
        other.get_lat_lon()
        # Use haversine formula
        try:
            lon1, lat1, lon2, lat2 = map(radians,
                                [self._lon, self._lat, other._lon, other._lat])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            c = 2 * asin(sqrt(a))
            dist = 6367 * c
        except Exception:
            raise Usage("Unable to compute distance from %s to %s" % (self, other))
        return dist

    # --------------------------------
    def geocode(self):
        """ Returns geocoded coords (cached or from Google).
        There is a 2500 query limit per day, may fail.
        Google geocode license restricted to Google Maps """

        # If found in cache, return coords
        if self._address in Location._geocode_cache:
            lat, lon = Location._geocode_cache[self._address]
            self.set_lat_lon(lat, lon)
            return

        # Real geocoding begins here
        try:
            conn = httplib.HTTPSConnection("maps.googleapis.com")
            params = {'sensor' : 'false', 'address' : self._address}
            url = "/maps/api/geocode/xml?" + urllib.urlencode(params)
            conn.request("GET", url)
            r = conn.getresponse()
            if r.status == 200:
                geo_xml = r.read()
                if geo_xml:
                    # Find lat, lon in returned XML
                    t = xml.etree.ElementTree.fromstring(geo_xml)
                    lat = t.findall('result/geometry/location/lat')
                    lon = t.findall('result/geometry/location/lng')
                    if lat and lon:
                        # Successful
                        self.set_lat_lon(float(lat[0].text),
                                         float(lon[0].text))
                        return
                    else:
                        err = "couldn't resolve address to lat,lon. Try another."
                else:
                    err = "not responding. Try later"
            else:
                err = "or network failure. Try later"
        except Exception:
            err = "exception"
        if err:
            raise Usage("Google geocoder " + err)

    # --------------------------------
    @staticmethod
    def load_cache():
        """ Loads cached location data from file """
        Location._geocode_cache = Cache.get_file_objects(Location._geocode_cache_name)

    # --------------------------------
    @staticmethod
    def save_cache():
        """ Saves cached location data into file """
        Cache.put_file_objects(Location._geocode_cache_name, Location._geocode_cache)

# -------------------------------------------------------------------------------
# Station
#
# Represents a caltrain station.
# Station objects are cached in the class to avoid duplication.
# -------------------------------------------------------------------------------
class Station(object):

    # Class dict of all known station objects by name
    _stations_cache = {}

    # --------------------------------
    def __init__(self, name):
        """ Init station location by adding search terms """
        self._name = name.lower().strip()
        address = self._name + " train station california"
        self._location = Location(address=address)

    # --------------------------------
    def __str__(self):
        """ Return string representation """
        return self._name

    # --------------------------------
    def __eq__(self, other):
        """ Compares station with other """
        return self._name == other._name

    # --------------------------------
    def is_named(self, name):
        """ Returns true if station name matches given """
        return self._name == name.lower().strip()

    # --------------------------------
    def distance_to(self, location):
        """ Returns distance to other location """
        return self._location.distance_to(location)

    # --------------------------------
    @staticmethod
    def find(name):
        """ Retrieves station obj from cache or creates new obj """
        name = name.lower().strip()
        if name not in Station._stations_cache:
            Station._stations_cache[name] = Station(name)
        return Station._stations_cache[name]

    # --------------------------------
    @staticmethod
    def forget(station_name):
        """ Removes named station from cache """
        if station_name in Station._stations_cache:
            del Station._stations_cache[station_name]

    # --------------------------------
    @staticmethod
    def geocode_all():
        """ Cause all cached stations to geocode """
        for st_name in Station._stations_cache:
            Station._stations_cache[st_name]._location.geocode()

# -------------------------------------------------------------------------------
# Schedule
#
# Represents a schedule (weekday, weekend, northbound, southbound). It consists
# of a name, stations list and times list. Stations and times lists are the
# same length. Each time list contains Time objects.
# Essentially, this is a matrix. Two stations connect if their time lists
# have valid times at identical indices, as this implies a train is common
# to both stations.
# -------------------------------------------------------------------------------
class Schedule(object):

    # --------------------------------
    def __init__(self, name):
        """ Default constructor """
        self._stations = []
        self._times = []
        self._name = name

    # --------------------------------
    def __str__(self):
        """ Return string representation """
        return self._name

    # --------------------------------
    def name(self):
        """ Return schedule name """
        return self._name

    # --------------------------------
    def add_station_with_times(self, name, times):
        """ Adds station (from cache) and times list to schedule """
        st = Station.find(name)
        self._stations.append(st)
        self._times.append(times)

    # --------------------------------
    def find_station(self, name):
        """ Returns station matching given name or None """
        for st in self._stations:
            if st.is_named(name):
                return st
        return None

    # --------------------------------
    def delete_station(self, name):
        """ If found, removes named station from schedule """
        st = self.find_station(name)
        if st:
            idx = self._stations.index(st)
            del self._stations[idx]
            del self._times[idx]

    # --------------------------------
    def find_nearest_station(self, location):
        """ Returns station nearest to given location or None.
        Since schedules can reference different stations
        this search must be tied to schedule instances """
        nearest = None
        dist = float('inf')
        for st in self._stations:
            loc_dist = st.distance_to(location)
            if loc_dist < dist:
                nearest = st
                dist = loc_dist
        return nearest

    # --------------------------------
    def list_stations(self):
        """ Return schedule's station names list """
        return map(str, self._stations)

    # --------------------------------
    def print_details(self, single_station_name=None):
        """ Print formatted schedule table and times """
        print '-'*80
        print self._name
        print '-'*80
        for idx in xrange(len(self._stations)):
            if single_station_name:
                if not self._stations[idx].is_named(single_station_name):
                    continue
            print self._stations[idx]
            # Gather all valid departures sorted ascending
            times = []
            for t in self._times[idx]:
                if t.is_valid():
                    times.append(str(t))
            times.sort()
            times = ", ".join(times)
            for line in wrap(times, 72):      # As needed
                print '\t', line
        print

    # --------------------------------
    def is_valid_direction(self, orig_name, dest_name):
        """ Return True if origin, destination in correct direction
         including going from station to self """
        st_names = self.list_stations()
        try:
            return st_names.index(orig_name) <= st_names.index(dest_name)
        except ValueError:
            return False

    # --------------------------------
    def get_earliest(self, when, orig_name, dest_name):
        """ Return earliest route from origin to destination """
        earliest = None
        if self.is_valid_direction(orig_name, dest_name):
            st_names = self.list_stations()
            cur_time = Time()
            cur_time.set(when.strftime("%I:%M"), 12 if when.time().hour >= 12 else 0)
            orig_times = self._times[st_names.index(orig_name)]
            dest_times = self._times[st_names.index(dest_name)]
            for i in xrange(len(orig_times)):
                if orig_times[i].is_valid() and dest_times[i].is_valid():
                    # If origin time less than current, skip times
                    if orig_times[i] < cur_time:
                        continue
                    # Save earliest of all matches
                    if not earliest:
                        earliest = orig_times[i]
                    elif orig_times[i] < earliest:
                        earliest = orig_times[i]
        return str(earliest) if earliest else None

    # --------------------------------
    def get_fastest(self, when, orig_name, dest_name, all):
        """ Return fastest routes from origin to destination. If
        all is true, returns a list of lists of durations and
        lists of departure times for each duration. If all is
        false returns the single fastest time and duration """
        durations = {}
        if self.is_valid_direction(orig_name, dest_name):
            st_names = self.list_stations()
            orig_times = self._times[st_names.index(orig_name)]
            dest_times = self._times[st_names.index(dest_name)]
            cur_time = Time()
            cur_time.set(when.strftime("%I:%M"), 12 if when.time().hour >= 12 else 0)
            for i in xrange(len(orig_times)):
                if orig_times[i].is_valid() and dest_times[i].is_valid():
                    # If origin time less than current, skip times
                    if orig_times[i] < cur_time:
                        continue
                    delta = orig_times[i].time_delta(dest_times[i])
                    if delta not in durations:
                        durations[delta] = []
                    durations[delta].append(orig_times[i])
        if durations:
            # Build dict of increasing durations and their respective dep times
            sorted_durations = sorted(durations.keys())
            result = []
            if not all:
                sorted_durations = sorted_durations[0:1]
                del durations[sorted_durations[0]][1:]
            # List of: dicts of: duration -> times list
            for d in sorted_durations:
                result.append({str(d) : map(str, durations[d])})
            return result
        else:
            return None

# -------------------------------------------------------------------------------
# RoutePlanner
#
# Represents high-level user functions for calculating routes. Tracks all
# schedules and decides which ones to use based on dates, start, end points.
# Builds schedules using parser.
# Some caltrain schedule caveats are not yet represented, like "saturday only"
# trains, but can be extended to do so.
# -------------------------------------------------------------------------------
class RoutePlanner(object):

    # --------------------------------
    def load(self, rebuild_cache = False):
        """ Create all objects needed for route planning. This method
        should be called when preparing to use the route planner. """
        debug("RoutePlanner.load, rebuild cache: %s" % rebuild_cache)
        self._cache_file_path = 'caltrain_route_cache.txt'

        # Load schedules cache file
        if rebuild_cache:
            cache_objects = None
        else:
            cache_objects = Cache.get_file_objects(self._cache_file_path)
        if cache_objects:
            # Read all four schedules from cache
            (self._weekday_northbound,
            self._weekday_southbound,
            self._weekend_northbound,
            self._weekend_southbound) = cache_objects
        else:
            # No cache or couldn't read. Fetch from web page
            parser = ScheduleParser()
            self._weekday_northbound = parser.make_schedule(True, True)
            self._weekday_southbound = parser.make_schedule(True, False)
            self._weekend_northbound = parser.make_schedule(False, True)
            self._weekend_southbound = parser.make_schedule(False, False)

            # Special case remove SJ bus arrivals from weekend table
            # as they are duplicates of SJ station. Keep lowercase.
            # Nasty hack, Caltrain didn't even use the same abbreviation
            # for north and south schedules. WTF.
            self._weekend_northbound.delete_station("s.j.")
            self._weekend_southbound.delete_station("sj")
            # Also remove from Station cache
            Station.forget("s.j")
            Station.forget("sj")

            # Force geocoding of all stations in all schedules since
            # they will be used often. This updates location cache.
            Station.geocode_all()

            # Force save location cache
            Location.save_cache()

            # Save schedules cache file
            cache_objects = (self._weekday_northbound,
                        self._weekday_southbound,
                        self._weekend_northbound,
                        self._weekend_southbound)
            Cache.put_file_objects(self._cache_file_path, cache_objects)

    # --------------------------------
    def list_stations(self):
        """ Return sorted list of all stations from all schedules.
        Could be improved by returning Station class cache, but that
        needs to be fixed to remove stations that were deleted. So
        using this set combining instead. """
        all = self._weekday_northbound.list_stations() + \
                self._weekday_southbound.list_stations() + \
                self._weekend_northbound.list_stations() + \
                self._weekend_southbound.list_stations()
        return sorted(list(set(all)))

    # --------------------------------
    def get_earliest(self, when, start_location, destination_name):
        """ Returns origin name and dep time for earliest route """
        origin_name, schedule = self._select_departure(when,
                                    start_location, destination_name)
        dep_time = None
        if schedule:
            dep_time = schedule.get_earliest(when, origin_name,
                                             destination_name)
        return origin_name, dep_time

    # --------------------------------
    def get_fastest(self, when, start_location, destination_name, all):
        """ Returns nearest origin name and:
            1. dep time for fastest route
                OR if all
            2. dict of durations and their dep times.
        """
        origin_name, schedule = self._select_departure(when,
                                    start_location, destination_name)
        dep_times = None
        if schedule:
            dep_times = schedule.get_fastest(when, origin_name,
                                               destination_name, all)
        return origin_name, dep_times

    # --------------------------------
    def print_stations(self):
        print ', '.join(self.list_stations())

    # --------------------------------
    def print_schedules(self, single_station_name=None):
        """ Prints single or all schedules to console """
        self._weekday_northbound.print_details(single_station_name)
        self._weekday_southbound.print_details(single_station_name)
        self._weekend_northbound.print_details(single_station_name)
        self._weekend_southbound.print_details(single_station_name)

    # --------------------------------
    def is_valid_station_name(self, station_name):
        """ Returns true if given station name exists in any schedule """
        all_names = self.list_stations()
        return station_name in all_names

    # --------------------------------
    def _select_departure(self, when, start_location, destination_name):
        """ Returns station name and schedule for given route and day
        or none if unable to connect """
        if when.weekday() >= 5:
            nb = self._weekend_northbound   # Sat - Sun
            sb = self._weekend_southbound
        else:
            nb = self._weekday_northbound   # Mon - Fri
            sb = self._weekday_southbound
        # Find nearest station to start location.
        # It's same for north or south bound, so use north
        origin_station = nb.find_nearest_station(start_location)
        origin_name = str(origin_station)
        # Choose north or south schedule. May be in neither
        if nb.is_valid_direction(origin_name, destination_name):
            schedule = nb
        elif sb.is_valid_direction(origin_name, destination_name):
            schedule = sb
        else:
            # destination name in neither N/S schedule. Fail
            schedule = None
        return origin_name, schedule

# -------------------------------------------------------------------------------
# Usage
#
# Prints command-line usage instructions
# -------------------------------------------------------------------------------
class Usage(Exception):

    # --------------------------------
    def __init__(self, msg=None):
        """ Default constructor """
        super(Exception, self).__init__(self)
        if msg:
            self.msg = msg
        else:
            self.msg = """

Usage: caltrain [-fansjz] [-d date] [-t time] [-c coords] [-g address] destination
    -d  Route from given date (uses current otherwise)
    -t  Route from given time (uses current otherwise)
    -c  Route from coordinates lat,lon (with comma)
    -g  Route from geocoded text (address, city, etc)
    -f  Return fastest route and duration
    -a  Return all routes (only for fastest)
    -n  Display all valid station names
    -s  Display all schedules (stations and times)
    -j  Display output in JSON (only works on some options)
    -z  Rebuild cache files

    destination - station name (use -n for valid names list)

Returns caltrain station and route information.

Unless requesting fastest route, the app will return the nearest station with
a departure that takes you to the destination the soonest (i.e. arrive ASAP).

With no options, the default behavior is to display the destination schedule.

Examples:

    Display Millbrae schedule:
        caltrain.py 'Millbrae'

    Display next departure from station nearest to coordinates stopping in San Mateo.

        caltrain.py -c 37.4484914,-122.1802812 'San Mateo'

    Display all next fastest-ordered routes to Sunnyvale from station nearest to
    SFO Starbucks, in JSON format.

        caltrain.py -faj -g 'Starbucks, SFO', 'Sunnyvale'
    
    Will result in two Millbrae departures, with durations of 0:49:00:

        [
            "millbrae", 
            [
                {
                    "0:49:00": [
                    "23:04", 
                    "00:25"
                    ]
                }
            ]
        ]

    Display next departure from station nearest to 'La Cumbre Taqueria' in San Mateo
    and stopping in Santa Clara, assuming given date and time as current.

        caltrain.py -d 4-29-2014 -t 17:15 -g 'Le Boulanger, Sunnyvale, CA', 'Palo Alto'

"""
# -------------------------------------------------------------------------------
# main
#
# Main entry point to application. Glad you figured it out before reading this.
# -------------------------------------------------------------------------------
def main(argv=None):

    if argv is None:
        argv = sys.argv
    try:
        # Init operation defaults
        earliest = True
        now = datetime.now()
        dep_date = now.date()
        dep_time = now.time()
        all_routes = False
        output_JSON = False
        display_station_names = False
        display_schedules = False
        coordinates = None
        address = None
        location = None
        rebuild_cache = False

        try:
            # Extract options and non-option arguments
            opts, args = getopt.getopt(argv[1:], "fansjzd:t:c:g:", ["help"])
        except getopt.error, msg:
            raise Usage(msg)

        # Process options and option arguments
        for o, a in opts:
            if o in ("--help"):
                raise Usage()
            elif o in ("-f"):
                earliest = False
            elif o in ("-c"):
                coordinates = a.strip()
            elif o in ("-g"):
                address = a.strip()
            elif o in ("-a"):
                all_routes = True
            elif o in ("-n"):
                display_station_names = True
            elif o in ("-s"):
                display_schedules = True
            elif o in ("-j"):
                output_JSON = True
            elif o in ("-z"):
                rebuild_cache = True
            elif o == "-d":
                try:
                    dep_date = datetime.strptime(a, '%m-%d-%Y').date()
                except ValueError:
                    raise Usage("Use date format mm-dd-yyyy")
            elif o == "-t":
                try:
                    dep_time = datetime.strptime(a, '%H:%M').time()
                except ValueError:
                    raise Usage("Use 24-hour time format HH:MM")
            else:
                assert False, "Unknown option"

        # Init planner to do all work
        rp = RoutePlanner()

        if display_station_names:
            rp.load(rebuild_cache)
            rp.print_stations()
        elif display_schedules:
            rp.load(rebuild_cache)
            rp.print_schedules()
        else:
            # Should have only destination station name argument
            if len(args) != 1:
                raise Usage()

            rp.load(rebuild_cache)

            # Create location from coordinates if given. Otherwise create
            # from address if that was given
            if coordinates:
                try:
                    # Check coords integrity
                    coordinates = coordinates.split(',')
                    lat=float(coordinates[0])
                    lon=float(coordinates[1])
                    location = Location(lat=lat, lon=lon, dont_cache=True)
                except ValueError:
                    raise Usage("Invalid coordinates. Check format.")
            elif address:
                location = Location(address=address, dont_cache=True)

            # Init and check destination station name
            destination = str(args[0]).lower().strip()
            if not rp.is_valid_station_name(destination):
                raise Usage("Unknown station name. Use -n to display list.")

            # If location found, try routing to destination
            if location:
                # Make current date/time
                when = datetime.combine(dep_date, dep_time)
                if earliest:
                    origin_station, result = rp.get_earliest(when, location, destination)
                else:
                    origin_station, result = rp.get_fastest(when, location, destination, all_routes)

                # Output results in JSON or plain
                if result:
                    if output_JSON:
                        print json.dumps((origin_station, result), indent=2)
                    else:
                        print (origin_station, result)
                else:
                    if origin_station:
                        raise Usage("No routes from nearest station: " + origin_station)
                    else:
                        raise Usage("Could not determine nearest station")
            else:
                # No location. Give info on destination station
                rp.print_schedules(destination)

    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, "for help use --help"
        return 2

if __name__ == "__main__":
    sys.exit(main())
