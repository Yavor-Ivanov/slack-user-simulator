#! /usr/bin/env python
# coding=utf-8

from slacker import Slacker
import os, ujson, itertools, random, copy, sys, safygiphy
from flask import Flask, request, Response
from settings import *


reload(sys)
sys.setdefaultencoding('utf8')


class DictAttr(dict):
    def __init__(self, *a, **ka):
        dict.__init__(self, *a, **ka)
        self.__dict__ = self


def listify(x):
    if not isinstance(x, (tuple, list)):
        return [x]
    return x


def get_channel_history(slacker, channel):
    messages = []
    ts = None
    while True:
        # NOTE<Yavor>: The max number of history entries allowed to be retrieved
        #              by the Slack API at one time is 1000.
        hist = slacker.channels.history(channel=channel, count=1000, latest=ts).body
        messages.extend(hist['messages'])
        ts = messages[-1]['ts']
        if not hist.get('has_more', False):
            break
    return messages


def flatten_channel_history(hist):
    def srt(u, t, d):
        msgs = d.get(u, [])
        msgs.append(t)
        d[u] = msgs
    usr2msg = dict()
    [srt(o['user'], o['text'], usr2msg) for o in hist if o.get('user', False) and o.get('subtype', None) is None]
    return usr2msg


# TODO<Yavor>: Collapse both keying functions.
def key_users(users):
    name2dict = DictAttr()
    def srt(u, d):
        u = DictAttr(u)
        d[u.name] = u
    [srt(u, name2dict) for u in users if u.get('is_bot', True) == False]
    return name2dict


def key_channels(channels):
    name2dict = DictAttr()
    def srt(c, d):
        c = DictAttr(c)
        d[c.name] = c
    [srt(c, name2dict) for c in channels]
    return name2dict


# TODO<Yavor>: Add update thread.
def update_cache(contents):
    with open(HISTORY_FILE, 'w') as f:
        ujson.dump(contents, f)


def get_cache():
    if os.path.isfile(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return DictAttr(ujson.loads(f.read()))
    return None


s = Slacker(API_KEY)
c = get_cache()
if c is None:
    print "Building cache..."
    c = DictAttr()
    c.users = key_users(s.users.list().body['members'])
    c.channels = key_channels(s.channels.list().body['channels'])
    c.groups = key_channels(s.groups.list().body['groups'])
    chan2hist = [flatten_channel_history(get_channel_history(s, chan.id)) for chan in c.channels.values()]
    c.hist = dict()
    for chan in chan2hist:
        for user, hist in chan.iteritems():
            c.hist[user] = c.hist.get(user, []) + hist
    update_cache(c)
    print "Updated!"


token2user = dict()
for user, alias in user2aliases.iteritems():
    alias = listify(alias)
    for a in alias:
        token2user[a] = user


app = Flask(__name__)
@app.route('/slack', methods=['POST'])
def inbound():
    def error_message(chan, msg):
        # TODO<Yavor>: Get the actual ABBY user, instead of hard coding the values.
        image = 'https://avatars.slack-edge.com/2015-02-06/3643462404_60e8e28596e711b08950_48.jpg'
        g = safygiphy.Giphy()
        r = g.random(tag="sorry motorcycle")
        s.chat.post_message(chan, 'Сори мотори! %s %s' % (msg, r['data']['image_original_url']),
                            username="ABBY BOT", as_user=False, icon_url=image)
        return Response(), 200

    if request.form.get('token') == WEBHOOK_SECRET:
        chan = request.form.get('channel_id')
        token = (request.form.get('text')).rsplit('?', 1)[0]
        username = token2user.get(token, token)
        u = c.users.get(username)
        if u is None:
            return error_message(chan, "Не познавам колегата `%s`." % username)
        user_messages = c.hist.get(u['id'])
        if len(user_messages) < MIN_MESSAGE_COUNT:
            return error_message(chan, "`%s` има < 50 съобщения." % username)
        # TODO<Yavor>: Detect giphy commands and pull a url.
        # TODO<Yavor>: Add protection from token recursion.
        s.chat.post_message(chan, random.choice(user_messages),
                            username=u['profile']['real_name'],
                            as_user=False,
                            icon_url=u['profile']['image_48'])
    return Response(), 200


if __name__ == "__main__":
    tokens = set(token2user.keys()) | set(c.users.keys())
    print "Token list:"
    print "--------------------"
    print reduce(lambda x, y: "%s?,%s" % (x, y), tokens) + "?"
    print "--------------------"
    app.run(host='0.0.0.0', port=PORT, debug=False)
