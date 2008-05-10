
import sys
import time
from dateutil.parser import parse
from ConfigParser import ConfigParser
from heapq import heappop, heappush
import traceback

from api import Twitter

try:
    import irclib
except:
    raise ImportError(
        "This module requires python irclib available from "
        + "http://python-irclib.sourceforge.net/")

def debug(msg):
    # uncomment this for debug text stuff
    print >> sys.stderr, msg
    pass

class SchedTask(object):
    def __init__(self, task, delta):
        self.task = task
        self.delta = delta
        self.next = time.time()

    def __repr__(self):
        return "<SchedTask %s next:%i delta:%i>" %(
            self.task.__name__, self.next, self.delta)
    
    def __cmp__(self, other):
        return cmp(self.next, other.next)
    
    def __call__(self):
        return self.task()

class Scheduler(object):
    def __init__(self, tasks):
        self.task_heap = []
        for task in tasks:
            heappush(self.task_heap, task)
    
    def next_task(self):
        now = time.time()
        task = heappop(self.task_heap)
        wait = task.next - now
        if (wait > 0):
            time.sleep(wait)
        task()
        task.next = now + task.delta
        heappush(self.task_heap, task)
        debug("tasks: " + str(self.task_heap))
        
    def run_forever(self):
        try:
            while True:
                self.next_task()
        except KeyboardInterrupt:
            pass
            
class TwitterBot(object):
    def __init__(self, configFilename):
        self.configFilename = configFilename
        self.config = load_config(self.configFilename)
        self.irc = irclib.IRC()
        self.irc.add_global_handler('privmsg', self.handle_privmsg)
        self.ircServer = self.irc.server()
        self.twitter = Twitter(
            self.config.get('twitter', 'email'),
            self.config.get('twitter', 'password'))
        self.sched = Scheduler(
            (SchedTask(self.process_events, 1),
             SchedTask(self.check_statuses, 60)))
        self.lastUpdate = time.gmtime()

    def check_statuses(self):
        debug("In check_statuses")
        try:
            updates = self.twitter.statuses.friends_timeline()
        except Exception, e:
            print >> sys.stderr, "Exception while querying twitter:"
            traceback.print_exc(file=sys.stderr)
            return
        
        for update in updates:
            crt = parse(update['created_at']).utctimetuple()
            if (crt > self.lastUpdate):
                self.privmsg_channel(
                    "=^_^= %s %s" %(
                        update['user']['screen_name'],
                        update['text']))
                self.lastUpdate = crt
            else:
                break

    def process_events(self):
        debug("In process_events")
        self.irc.process_once()
    
    def handle_privmsg(self, conn, evt):
        debug('got privmsg')
        args = evt.arguments()[0].split(' ')
        try:
            if (not args):
                return
            if (args[0] == 'follow' and args[1:]):
                self.follow(conn, evt, args[1])
            elif (args[0] == 'unfollow' and args[1:]):
                self.unfollow(conn, evt, args[1])
            else:
                conn.privmsg(
                    evt.source().split('!')[0], 
                    "=^_^= Hi! I'm Twitterbot! you can (follow "
                    + "<twitter_name>) to make me follow a user or "
                    + "(unfollow <twitter_name>) to make me stop.")
        except Exception:
            traceback.print_exc(file=sys.stderr)

    def privmsg_channel(self, msg):
        return self.ircServer.privmsg(
            self.config.get('irc', 'channel'), msg)
            
    def follow(self, conn, evt, name):
        userNick = evt.source().split('!')[0]
        friends = [x['name'] for x in self.twitter.statuses.friends()]
        debug("Current friends: %s" %(friends))
        if (name in friends):
            conn.privmsg(
                userNick,
                "=O_o= I'm already following %s." %(name))
        else:
            self.twitter.friendships.create(id=name)
            conn.privmsg(
                userNick,
                "=^_^= Okay! I'm now following %s." %(name))
            self.privmsg_channel(
                "=o_o= %s has asked me to start following %s" %(
                    userNick, name))
    
    def unfollow(self, conn, evt, name):
        userNick = evt.source().split('!')[0]
        friends = [x['name'] for x in self.twitter.statuses.friends()]
        debug("Current friends: %s" %(friends))
        if (name not in friends):
            conn.privmsg(
                userNick,
                "=O_o= I'm not following %s." %(name))
        else:
            self.twitter.friendships.destroy(id=name)
            conn.privmsg(
                userNick,
                "=^_^= Okay! I've stopped following %s." %(name))
            self.privmsg_channel(
                "=o_o= %s has asked me to stop following %s" %(
                    userNick, name))
    
    def run(self):
        self.ircServer.connect(
            self.config.get('irc', 'server'), 
            self.config.getint('irc', 'port'),
            self.config.get('irc', 'nick'))
        self.ircServer.join(self.config.get('irc', 'channel'))
        try:
            self.sched.run_forever()
        except KeyboardInterrupt:
            pass

def load_config(filename):
    defaults = dict(server=dict(port=6667, nick="twitterbot"))
    cp = ConfigParser(defaults)
    cp.read((filename,))
    return cp

def main():
    configFilename = "twitterbot.ini"
    if (sys.argv[1:]):
        configFilename = sys.argv[1]
    bot = TwitterBot(configFilename)
    return bot.run()