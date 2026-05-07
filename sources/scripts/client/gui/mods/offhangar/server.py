# scripts/client/gui/mods/offhangar/server.py

"""
FakeServer — подменяет серверное взаимодействие для оффлайн-режима.
"""

import BigWorld
import functools
import AccountCommands
import cPickle

from gui.mods.offhangar._constants import CHAT_ACTION_DATA
from gui.mods.offhangar.logging import LOG_DEBUG

BASE_REQUESTS = {}


class FakeServer(object):
    def __call__(self, *args, **kwargs):
        if not self.__isMuted:
            LOG_DEBUG('%s ( %s, %s )' % (self.__name, args, kwargs))

    def __init__(self, name='Server', isMuted=False):
        super(FakeServer, self).__init__()
        self.__isMuted = isMuted
        self.__name    = name

    def __getattr__(self, name):
        try:
            return super(FakeServer, self).__getattribute__(name)
        except AttributeError:
            return FakeServer(
                name='%s.%s' % (self.__name, name),
                isMuted=self.__isMuted
            )

    def chatCommandFromClient(
            self, requestID, action, channelID,
            int64Arg, int16Arg, stringArg1, stringArg2):
        try:
            chatActionData = CHAT_ACTION_DATA.copy()
            chatActionData['requestID'] = requestID
            chatActionData['action']    = action
            BigWorld.player().onChatAction(chatActionData)
        except:
            pass

    def doCmdStr(self, requestID, cmd, s):
        self.__doCmd(requestID, cmd, s)

    def doCmdIntStr(self, requestID, cmd, i, s):
        self.__doCmd(requestID, cmd, i, s)

    def doCmdInt3(self, requestID, cmd, int1, int2, int3):
        self.__doCmd(requestID, cmd, int1, int2, int3)

    def doCmdInt4(self, requestID, cmd, int1, int2, int3, int4):
        self.__doCmd(requestID, cmd, int1, int2, int3, int4)

    def doCmdInt2Str(self, requestID, cmd, int1, int2, s):
        self.__doCmd(requestID, cmd, int1, int2, s)

    def doCmdIntArr(self, requestID, cmd, arr):
        self.__doCmd(requestID, cmd, arr)

    def doCmdIntArrStrArr(self, requestID, cmd, intArr, strArr):
        self.__doCmd(requestID, cmd, intArr, strArr)

    def prb_createTrainingRoom(self, arenaTypeID, roundLength, isPrivate, comment):
        try:
            import ArenaType
            from constants import ARENA_GUI_TYPE
            from gui.mods.mod_observer import g_instance
            g_instance.arenaType    = ArenaType.g_cache[arenaTypeID]
            g_instance.spaceName    = g_instance.arenaType.geometryName
            g_instance.arenaGuiType = ARENA_GUI_TYPE.TRAINING
            BigWorld.callback(0.3, g_instance.observerStart)
        except Exception as e:
            LOG_DEBUG('Error creating training room: %s' % str(e))

    def prb_join(self, *args):              pass
    def prb_leave(self, *args):             pass
    def prb_notReady(self, *args):          pass
    def prb_assign(self, *args):            pass
    def prb_requestPlayerData(self, *args): pass
    def prb_kick(self, *args):              pass
    def prb_swap(self, *args):              pass
    def prb_changeSettings(self, *args):    pass
    def prb_createSquad(self, *args):       pass
    def prb_sendInvites(self, *args):       pass
    def prb_destroyTrainingRoom(self, *args): pass

    def prb_ready(self, *args):
        try:
            from gui.mods.mod_observer import g_instance
            if g_instance.arenaType is not None and not g_instance.isStarted:
                BigWorld.callback(0.1, g_instance.observerStart)
        except Exception as e:
            LOG_DEBUG('Error in prb_ready: %s' % str(e))

    def prb_startBattle(self, *args):
        try:
            from gui.mods.mod_observer import g_instance
            if not g_instance.isStarted:
                BigWorld.callback(0.1, g_instance.observerStart)
        except Exception as e:
            LOG_DEBUG('Error in prb_startBattle: %s' % str(e))

    def prb_changeArena(self, arenaTypeID, *args):
        try:
            import ArenaType
            from gui.mods.mod_observer import g_instance
            if arenaTypeID in ArenaType.g_cache:
                g_instance.arenaType = ArenaType.g_cache[arenaTypeID]
                g_instance.spaceName = g_instance.arenaType.geometryName
                g_instance.onUpdate()
        except Exception as e:
            LOG_DEBUG('Error changing arena: %s' % str(e))

    def __doCmd(self, requestID, cmd, *args):
        try:
            cmdCall = BASE_REQUESTS.get(cmd)
            if cmdCall:
                requestID, resultID, errorStr, ext = cmdCall(requestID, *args)
            else:
                LOG_DEBUG('Unknown cmd: %s' % cmd)
                requestID, resultID, errorStr, ext = (
                    requestID, AccountCommands.RES_FAILURE, '', None
                )

            player = BigWorld.player()

            if ext is not None:
                callback = functools.partial(
                    player.onCmdResponseExt,
                    requestID, resultID, errorStr, cPickle.dumps(ext)
                )
            else:
                callback = functools.partial(
                    player.onCmdResponse,
                    requestID, resultID, errorStr
                )

            BigWorld.callback(0.0, callback)

        except Exception as e:
            LOG_DEBUG('Error in __doCmd: %s' % str(e))
            import traceback
            LOG_DEBUG(traceback.format_exc())