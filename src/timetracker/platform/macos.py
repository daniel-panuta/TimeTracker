from Cocoa import NSWorkspace, NSObject, NSRunLoop, NSDate, NSTimer
import objc, datetime as dt, time, os, sqlite3
from ..core import ensure_rollover, ensure_mode
from ..db import connect
from ..logging_setup import get_logger

logger = get_logger("tt.macos")

class Observer(NSObject):
    def init(self):
        self = objc.super(Observer, self).init()
        if self is None: return None
        self.con = connect()
        ensure_rollover(self.con, logger)
        ensure_mode(self.con, "active", logger)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            60.0, self, objc.selector(self.tick_, signature=b'v@:@'), None, True
        )
        return self

    def tick_(self, _):
        ensure_rollover(self.con, logger)

    def sessionDidResignActive_(self, notif):
        ensure_rollover(self.con, logger)
        ensure_mode(self.con, "pause", logger)

    def sessionDidBecomeActive_(self, notif):
        ensure_rollover(self.con, logger)
        ensure_mode(self.con, "active", logger)

def run():
    obs = Observer.alloc().init()
    ws = NSWorkspace.sharedWorkspace().notificationCenter()
    ws.addObserver_selector_name_object_(
        obs, objc.selector(Observer.sessionDidResignActive_, signature=b'v@:@'),
        "NSWorkspaceSessionDidResignActiveNotification", None)
    ws.addObserver_selector_name_object_(
        obs, objc.selector(Observer.sessionDidBecomeActive_, signature=b'v@:@'),
        "NSWorkspaceSessionDidBecomeActiveNotification", None)
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.distantFuture())
