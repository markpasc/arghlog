from __future__ import division

from datetime import datetime
from itertools import chain, count, izip
from functools import wraps
import logging
import os
import os.path
from random import shuffle
import readline
import sys
from urllib import urlencode
from urlparse import parse_qsl, urlunsplit

try:
    import json
except ImportError:
    import simplejson as json

import argparse
from prettytable import PrettyTable
from progressbar import ProgressBar
from rdioapi import Rdio, httplib2


def configure_keys(args):
    if not args.consumer_token:
        args.consumer_token = raw_input('Consumer token: ')
    if not args.consumer_secret:
        args.consumer_secret = raw_input('Consumer secret: ')
    if not args.access_token:
        data_store = dict()
        logging.debug("TOKEN IS: %r", args.consumer_token)
        rdio = Rdio(args.consumer_token, args.consumer_secret, data_store)
        login_url = rdio.begin_authentication('oob')

        print "Open this URL in your web browser to get an API PIN:"
        print
        print "    ", login_url
        print
        verifier = raw_input("PIN: ")

        rdio.complete_authentication(verifier)

        assert data_store['access_token'], "Authentication did not provide an access token"
        logging.debug("ACCESS TOKEN: %r", data_store['access_token'])
        args.access_token = urlencode(data_store['access_token'])
    if not args.echonest_key:
        args.echonest_key = raw_input('Echo Nest API key (optional): ')

    filepath = os.path.expanduser('~/.%s' % os.path.basename(__file__))
    # Don't let anybody else read the config file.
    os.umask(077)
    with open(filepath, 'w') as config_file:
        config_file.write('--consumer-token\n')
        config_file.write(args.consumer_token)
        config_file.write('\n--consumer-secret\n')
        config_file.write(args.consumer_secret)
        config_file.write('\n--access-token\n')
        config_file.write(args.access_token)
        if args.echonest_key:
            config_file.write('\n--echonest-key\n')
            config_file.write(args.echonest_key)
        config_file.write('\n')

    print "Configured!"


def authd(fn):
    @wraps(fn)
    def moo(args, *pargs, **kwargs):
        data_store = {'access_token': dict(parse_qsl(args.access_token))}
        logging.debug("ACCESS TOKEN: %r", data_store['access_token'])
        rdio = Rdio(args.consumer_token, args.consumer_secret, data_store)
        return fn(rdio, args, *pargs, **kwargs)
    return moo


@authd
def list_playlists(rdio, args):
    playlists = rdio.getPlaylists()

    cols = ['Name', 'Owner', 'Relationship', 'Key']
    table = PrettyTable(cols)
    for col in cols:
        table.set_field_align(col, 'l')
    for pl in playlists['owned']:
        table.add_row([pl['name'], pl['owner'], 'Owner', pl['key']])
    for pl in playlists['collab']:
        table.add_row([pl['name'], pl['owner'], 'Collaborator', pl['key']])
    for pl in playlists['subscribed']:
        table.add_row([pl['name'], pl['owner'], 'Subscriber', pl['key']])
    table.printt()


def print_tracks_in_thing(rdio, thing):
    trackkeys = thing['trackKeys']
    trackdata = rdio.get(keys=','.join(trackkeys))
    tracks = [trackdata[trackkey] for trackkey in trackkeys]

    cols = ['#', 'Title', 'Artist', 'Album', 'Time', 'Key']
    table = PrettyTable(cols)
    table.set_field_align('#', 'r')
    for col in cols[1:]:
        table.set_field_align(col, 'l')
    for i, track in izip(count(1), tracks):
        duration_secs = track['duration']
        duration = '%d:%02d' % (duration_secs / 60, duration_secs % 60)
        table.add_row([i, track['name'], track['artist'], track['album'], duration, track['key']])
    table.printt()


def show_playlist(rdio, playlist, args):
    print "%(name)s\n%(owner)s\n%(shortUrl)s\n" % playlist
    print_tracks_in_thing(rdio, playlist)


def show_artist(rdio, artist, args):
    print "%(name)s\n%(length)d songs on %(albumCount)d albums\n%(shortUrl)s\n" % artist

    albums = rdio.getAlbumsForArtist(artist=artist['key'], featuring='true')

    cols = ['Name', 'Artist', 'Time', 'Key']
    table = PrettyTable(cols)
    for col in cols:
        table.set_field_align(col, 'l')
    for album in albums:
        duration_secs = album['duration']
        duration = '%d:%02d' % (duration_secs / 60, duration_secs % 60)
        table.add_row([album['name'], album['artist'], duration, album['key']])
    table.printt()


def show_album(rdio, album, args):
    duration_secs = album['duration']
    duration = '%d:%02d' % (duration_secs / 60, duration_secs % 60)
    print ("%(name)s\n%(length)d songs (%%s)\n%(shortUrl)s\n" % album) % (duration,)

    print_tracks_in_thing(rdio, album)


def show_track(rdio, track, args):
    cols = ['#', 'Title', 'Artist', 'Album', 'Time', 'Key']
    table = PrettyTable(cols)
    for col in cols:
        table.set_field_align(col, 'l')
    for track in (track,):
        duration_secs = track['duration']
        duration = '%d:%02d' % (duration_secs / 60, duration_secs % 60)
        table.add_row([track['trackNum'], track['name'], track['artist'], track['album'], duration, track['key']])
    table.printt()


@authd
def show_thing(rdio, args):
    things = rdio.get(keys=args.key, extras='trackKeys,albumCount')
    thing = things[args.key]

    show_funcs = {
        'p': show_playlist,
        'r': show_artist,
        'a': show_album,
        't': show_track,
    }

    thing_type = thing['type']
    try:
        func = show_funcs[thing_type]
    except KeyError:
        raise NotImplementedError('Unknown Rdio thing type %r' % thing_type)

    func(rdio, thing, args)


@authd
def sort_playlist(rdio, args):
    playlists = rdio.get(keys=args.playlist, extras='trackKeys')
    playlist = playlists[args.playlist]
    trackkeys = playlist['trackKeys']

    # Let's add the sorted tracks before deleting the existing ones, so
    # if deletion fails you have duplicates instead of an empty playlist.
    if args.by == 'key':
        # Abuse Rdio's auto-sort in addToPlaylist, instead of laborious
        # sorting and re-adding here.
        rdio.addToPlaylist(playlist=args.playlist, tracks=','.join(trackkeys))
    else:
        if args.by == 'shuffle':
            # We don't care about the track data, so don't fetch it.
            sorted_trackkeys = list(trackkeys)
            shuffle(sorted_trackkeys)
        else:
            trackdata = rdio.get(keys=','.join(trackkeys))
            sorted_tracks = sorted(trackdata.itervalues(), key=lambda x: x.get(args.by))
            sorted_trackkeys = [track['key'] for track in sorted_tracks]

        logging.debug('Original tracks: %r', trackkeys)
        logging.debug('Sorted tracks:   %r', sorted_trackkeys)

        # Apparently Rdio sorts tracks in addToPlaylist first (?!) so
        # we have to add them one by one.
        progress = ProgressBar()
        for trackkey in progress(sorted_trackkeys):
            rdio.addToPlaylist(playlist=args.playlist, tracks=trackkey)

    # Finally, remove the original order from the front of the playlist.
    rdio.removeFromPlaylist(playlist=args.playlist, index=0, count=len(trackkeys), tracks=','.join(trackkeys))

    logging.info('Sorted playlist "%s"', playlist['name'])


@authd
def search(rdio, args):
    query = ' '.join(chain(args.artist, args.album, args.track, args.query))
    logging.debug('Whole query is: %r', query)
    resultset = rdio.search(query=query, types='Artist,Album,Track', count=args.count)

    results = (result for result in resultset['results'] if result['type'] in ('t', 'a', 'r'))
    if args.artist:
        results = (result for result in results if ' '.join(args.artist).lower() in (result['name'] if result['type'] == 'r' else result['artist']).lower())
    if args.album:
        results = (result for result in results if ' '.join(args.album).lower() in (result['name'] if result['type'] == 'a' else result.get('album', '')).lower())
    if args.track:
        results = (result for result in results if result['type'] == 't' and ' '.join(args.track).lower() in result['name'].lower())

    cols = ['Track', 'Album', 'Artist', 'Key']
    table = PrettyTable(cols)
    for col in cols:
        table.set_field_align(col, 'l')
    for result in results:
        result_name = u'%(name)s' if result['type'] == 'r' else u'%(name)s by %(artist)s'
        if result['type'] == 't':
            table.add_row([result['name'], result['album'], result['artist'], result['key']])
        elif result['type'] == 'a':
            table.add_row(['', result['name'], result['artist'], result['key']])
        elif result['type'] == 'r':
            table.add_row(['', '', result['name'], result['key']])
        else:
            raise NotImplementedError("Unexpected Rdio object type %r in search results" % result['type'])
    table.printt()


@authd
def improvise_playlist(rdio, args):
    if not args.echonest_key:
        print "Echo Nest API key is required to improvise a playlist. See: http://developer.echonest.com/"
        return

    tracks = rdio.get(keys=args.track)
    track = tracks[args.track]
    trackname, artistname = track['name'], track['artist']

    query = {
        'api_key': args.echonest_key,
        'format': 'json',
        'song_id': 'rdio-us-streaming:song:%s' % args.track,
        'type': 'song-radio',
        'results': 25,
        'bucket': 'id:rdio-us-streaming',
        'limit': 'true',
    }
    url = urlunsplit(('http', 'developer.echonest.com', '/api/v4/playlist/static', urlencode(query), ''))

    http = httplib2.Http()
    resp, cont = http.request(url)
    if resp.status != 200:
        logging.error('Unexpected response from Echo Nest: %d %s', resp.status, resp.reason)
        return

    improv = json.loads(cont)
    logging.debug("Playlist response: %r", improv)
    if improv['response']['status']['code'] == 5:
        logging.error("Oops, Echo Nest doesn't know about the Rdio track %s by %s (%s).", trackname, artistname, args.track)
        return
    elif improv['response']['status']['code'] != 0:
        logging.error("Oops, Echo Nest said: %s", improv['response']['status']['message'])
        return

    improv_tracks = [song['foreign_ids'][0]['foreign_id'].rsplit(':', 1)[-1] for song in improv['response']['songs']]

    if args.playlist:
        playlistkey = args.playlist
        playlist = rdio.get(keys=playlistkey)[playlistkey]
        rdio.addToPlaylist(playlist=playlistkey, tracks=args.track)
    else:
        playlist = rdio.createPlaylist(name=datetime.now().strftime('Improvisation %Y-%m-%d'),
            description='Improvised from %s by %s (powered by Echo Nest)' % (trackname, artistname),
            tracks=args.track)
        playlistkey = playlist['key']

    progress = ProgressBar()
    for track in progress(improv_tracks):
        rdio.addToPlaylist(playlist=playlistkey, tracks=track)

    print "Playlist improvised into %s" % playlist['shortUrl']


def load_config_args():
    filepath = os.path.expanduser('~/.%s' % os.path.basename(__file__))
    if not os.path.exists(filepath):
        return list()

    with open(filepath, 'r') as config_file:
        config_args = [line.strip('\n') for line in config_file.readlines()]
    return config_args


def main(argv):
    config_args = load_config_args()
    args = config_args + argv

    parser = argparse.ArgumentParser(description='Control Rdio from the command line.')
    parser.set_defaults(verbosity=[2])
    parser.add_argument('-v', dest='verbosity', action='append_const', const=1, help='be more verbose (stackable)')
    parser.add_argument('-q', dest='verbosity', action='append_const', const=-1, help='be less verbose (stackable)')
    parser.add_argument('--consumer-token', help='Rdio API consumer token')
    parser.add_argument('--consumer-secret', help='Rdio API consumer secret')
    parser.add_argument('--access-token', help='Rdio access token (in web POST format)')
    parser.add_argument('--echonest-key', help='Echo Nest API key')
    subparsers = parser.add_subparsers(title='subcommands', metavar='COMMAND')

    parser_configure = subparsers.add_parser('configure', help='configures the API keys')
    parser_configure.set_defaults(func=configure_keys)

    parser_show = subparsers.add_parser('show', help='shows something to you')
    parser_show.set_defaults(func=show_thing)
    parser_show.add_argument('key', help='the key of the thing to show')

    parser_playlists = subparsers.add_parser('playlists', help='lists your playlists')
    parser_playlists.set_defaults(func=list_playlists)

    parser_sort = subparsers.add_parser('sort', help='sorts a playlist')
    parser_sort.set_defaults(func=sort_playlist)
    parser_sort.add_argument('playlist', help='the playlist key')
    parser_sort.add_argument('--by', default='key', help='the track property to sort by (try "artist" or ""; default "key")')

    parser_shuffle = subparsers.add_parser('shuffle', help='shuffles a playlist')
    parser_shuffle.set_defaults(func=sort_playlist, by='shuffle')
    parser_shuffle.add_argument('playlist', help='the playlist key')

    parser_search = subparsers.add_parser('search', help='search for something')
    parser_search.set_defaults(func=search)
    parser_search.add_argument('query', nargs='*', help='the text to search for')
    parser_search.add_argument('--artist', default=[], nargs='+', help='search text to require in the artist field')
    parser_search.add_argument('--album', default=[], nargs='+', help='search text to require in the album field')
    parser_search.add_argument('--track', default=[], nargs='+', help='search text to require in the track name field')
    parser_search.add_argument('--count', type=int, default=15, help='the number of results to show (default: 15)')

    parser_improvise = subparsers.add_parser('improvise', help='create a playlist similar to one track')
    parser_improvise.set_defaults(func=improvise_playlist)
    parser_improvise.add_argument('track', help='the track to improvise from (key)')
    parser_improvise.add_argument('--playlist', help='the playlist to append to (key; by default, makes a new playlist)')

    args = parser.parse_args(args)

    verbosity = sum(args.verbosity)
    verbosity = 0 if verbosity < 0 else verbosity if verbosity < 4 else 4
    log_level = (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)[verbosity]
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
    logging.info('Set log level to %s', logging.getLevelName(log_level))

    try:
        args.func(args)
    except KeyboardInterrupt:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
