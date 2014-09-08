__NOTOC__

=== What this is ===
A python Caltrain schedule web page parser and query app.

=== Caveats ===
The app will, upon reading the Caltrain schedule, save a cache file so that subsequent calls will load faster from this cache rather than fetch and re-parse the Caltrain page. Delete the cache files if you think they're stale.

=== Testing ===
I tested this on Mac OS X running Python 2.7.3. As of Sep 8, 2013 and the app parsed caltrain schedules successfully, but expect it to break in future as Caltrain changes their web page.

=== Command Line Usage ===
<pre>
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


    for help use --help
</pre>

=== License ===
Feel free to use for any purpose, with no restrictions, but please keep my copyright notice.

=== Example Output: Display Palo Alto Station Schedule ===
<pre>
    $ python caltrain.py 'Palo Alto'
    --------------------------------------------------------------------------------
    Weekday Northbound Schedule
    --------------------------------------------------------------------------------
    palo alto
        05:01, 05:36, 06:05, 06:23, 06:36, 07:05, 07:16, 07:23, 07:36, 08:05,
        08:16, 08:23, 08:36, 09:11, 09:41, 10:11, 10:41, 11:41, 12:41, 13:41,
        14:41, 15:11, 15:38, 16:16, 16:24, 16:43, 16:54, 17:06, 17:16, 17:24,
        17:43, 17:54, 18:06, 18:16, 18:24, 18:43, 18:54, 19:10, 19:21, 20:01,
        21:01, 22:01, 23:01

    --------------------------------------------------------------------------------
    Weekday Southbound Schedule
    --------------------------------------------------------------------------------
    palo alto
        00:57, 05:51, 06:21, 06:57, 07:18, 07:26, 07:36, 07:51, 08:01, 08:18,
        08:26, 08:36, 08:51, 09:01, 09:18, 09:26, 09:36, 10:03, 10:25, 11:03,
        12:03, 13:03, 14:03, 15:03, 15:25, 16:03, 16:25, 16:44, 17:01, 17:12,
        17:38, 17:49, 18:02, 18:12, 18:38, 18:49, 19:02, 19:12, 19:38, 20:26,
        21:36, 22:36, 23:36

    --------------------------------------------------------------------------------
    Weekend and Holiday Northbound Schedule
    --------------------------------------------------------------------------------
    palo alto
        07:31, 08:31, 09:31, 10:31, 10:58, 11:31, 12:31, 13:31, 14:31, 15:31,
        16:31, 17:31, 17:58, 18:31, 19:31, 20:31, 21:31, 23:01

    --------------------------------------------------------------------------------
    Weekend and Holiday Southbound Schedule
    --------------------------------------------------------------------------------
    palo alto
        01:03, 09:17, 10:17, 11:17, 12:17, 12:39, 13:17, 14:17, 15:17, 16:17,
        17:17, 18:17, 19:17, 19:39, 20:17, 21:17, 22:17, 23:17
</pre>
