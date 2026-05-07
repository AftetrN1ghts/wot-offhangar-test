# scripts/client/gui/mods/offhangar/requests.py

"""
Обработчики серверных команд.
Включает синхронизацию данных и команды покупок/продаж.
"""

import functools
from collections import namedtuple

import BigWorld
import AccountCommands
import zlib
import cPickle
import game

from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.server import BASE_REQUESTS, FakeServer
from gui.mods.offhangar._constants import REQUEST_CALLBACK_TIME
from gui.mods.offhangar.data import (
    getOfflineInventory,
    getOfflineStats,
    getOfflineShop,
    getOfflineQuestsProgress
)
from gui.mods.offhangar import account_state
from gui.mods.offhangar import shop_actions

RequestResult = namedtuple('RequestResult', ['resultID', 'errorStr', 'data'])


def packStream(requestID, data):
    try:
        data = zlib.compress(cPickle.dumps(data))
        desc = cPickle.dumps((len(data), zlib.crc32(data)))
        return functools.partial(game.onStreamComplete, requestID, desc, data)
    except Exception as e:
        LOG_DEBUG('Error in packStream: %s' % str(e))
        return None


def baseRequest(cmdID):
    def wrapper(func):
        def requester(requestID, *args):
            try:
                result = func(requestID, *args)
                return requestID, result.resultID, result.errorStr, result.data
            except Exception as e:
                LOG_DEBUG('Error in request %s: %s' % (cmdID, str(e)))
                import traceback
                LOG_DEBUG(traceback.format_exc())
                return requestID, AccountCommands.RES_FAILURE, str(e), None
        BASE_REQUESTS[cmdID] = requester
        return func
    return wrapper


def _triggerResync():
    """Запускает ресинхронизацию клиента после изменения данных"""
    try:
        player = BigWorld.player()
        if player and hasattr(player, 'resyncDossiers'):
            BigWorld.callback(0.1, lambda: None)  # placeholder
    except:
        pass


# ==================== Синхронизация ====================

@baseRequest(AccountCommands.CMD_COMPLETE_TUTORIAL)
def completeTutorial(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_SYNC_DATA)
def syncData(requestID, revision, crc, _):
    account_state.initialize()
    data = {'rev': revision + 1, 'prevRev': revision}
    data.update(getOfflineInventory())
    data.update(getOfflineStats())
    data.update(getOfflineQuestsProgress())
    return RequestResult(AccountCommands.RES_SUCCESS, '', data)


@baseRequest(AccountCommands.CMD_SYNC_SHOP)
def syncShop(requestID, revision, dataLen, dataCrc):
    data = {'rev': revision + 1, 'prevRev': revision}
    data.update(getOfflineShop())
    callback = packStream(requestID, data)
    if callback:
        BigWorld.callback(REQUEST_CALLBACK_TIME, callback)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_SYNC_DOSSIERS)
def syncDossiers(requestID, revision, maxChangeTime, _):
    callback = packStream(requestID, (revision + 1, []))
    if callback:
        BigWorld.callback(REQUEST_CALLBACK_TIME, callback)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


# ==================== Серверная информация ====================

@baseRequest(AccountCommands.CMD_REQ_SERVER_STATS)
def reqServerStats(requestID, *args):
    data = (0, {})
    callback = packStream(requestID, data)
    if callback:
        BigWorld.callback(REQUEST_CALLBACK_TIME, callback)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_REQ_PREBATTLES)
def reqPrebattles(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_REQ_PREBATTLES_BY_CREATOR)
def reqPrebattlesByCreator(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_REQ_PREBATTLE_ROSTER)
def reqPrebattleRoster(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# ==================== Настройки ====================

@baseRequest(AccountCommands.CMD_ADD_INT_USER_SETTINGS)
def addIntUserSettings(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_DEL_INT_USER_SETTINGS)
def delIntUserSettings(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_GET_AVATAR_SYNC)
def getAvatarSync(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# ==================== ПОКУПКА / ПРОДАЖА ТЕХНИКИ ====================

@baseRequest(AccountCommands.CMD_BUY_VEHICLE)
def cmdBuyVehicle(requestID, intCD, buyShells, recruitCrew, tmanCostIdx):
    """
    Покупка танка.
    arr: [intCD, buyShellsFlag, recruitCrewFlag, tmanCostIdx]
    """
    LOG_DEBUG('CMD_BUY_VEHICLE: intCD=%s shells=%s crew=%s cost=%s' % (
        intCD, buyShells, recruitCrew, tmanCostIdx))

    result = shop_actions.buyVehicle(
        intCD=intCD,
        buyShells=bool(buyShells),
        recruitCrew=bool(recruitCrew),
        tmanCostIdx=tmanCostIdx
    )

    if result.success:
        # Возвращаем обновлённые данные для ресинка
        syncResult = _buildSyncData()
        return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
    else:
        LOG_DEBUG('Buy vehicle failed: %s' % result.message)
        return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)


@baseRequest(AccountCommands.CMD_SELL_VEHICLE)
def cmdSellVehicle(requestID, *args):
    """
    Продажа танка.
    Первый аргумент из args — invID или массив с invID.
    """
    try:
        if args and isinstance(args[0], (list, tuple)):
            invID = args[0][0] if args[0] else -1
        elif args:
            invID = args[0]
        else:
            invID = -1

        LOG_DEBUG('CMD_SELL_VEHICLE: invID=%s args=%s' % (invID, args))

        result = shop_actions.sellVehicle(invID)

        if result.success:
            syncResult = _buildSyncData()
            return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
        else:
            LOG_DEBUG('Sell vehicle failed: %s' % result.message)
            return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)

    except Exception as e:
        LOG_DEBUG('cmdSellVehicle error: %s' % str(e))
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


# ==================== ПОКУПКА СЛОТОВ / КАЗАРМЫ ====================

@baseRequest(AccountCommands.CMD_BUY_SLOT)
def cmdBuySlot(requestID, *args):
    LOG_DEBUG('CMD_BUY_SLOT')
    result = shop_actions.buySlot()
    if result.success:
        syncResult = _buildSyncData()
        return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
    return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)


@baseRequest(AccountCommands.CMD_BUY_BERTHS)
def cmdBuyBerths(requestID, *args):
    LOG_DEBUG('CMD_BUY_BERTHS')
    result = shop_actions.buyBerths()
    if result.success:
        syncResult = _buildSyncData()
        return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
    return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)


# ==================== ОБМЕН ВАЛЮТЫ ====================

@baseRequest(AccountCommands.CMD_EXCHANGE)
def cmdExchange(requestID, goldAmount, *args):
    """Обмен золота на кредиты"""
    LOG_DEBUG('CMD_EXCHANGE: gold=%s' % goldAmount)
    result = shop_actions.exchangeGoldForCredits(goldAmount)
    if result.success:
        syncResult = _buildSyncData()
        return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
    return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)


# ==================== ЭКИПАЖ ====================

@baseRequest(AccountCommands.CMD_RECRUIT_TANKMAN)
def cmdRecruitTankman(requestID, *args):
    """Рекрутирование танкиста"""
    try:
        # Парсим аргументы — формат зависит от версии клиента
        if len(args) >= 4:
            nationID = args[0]
            vehicleTypeID = args[1]
            role = args[2]
            tmanCostIdx = args[3]
        elif len(args) >= 1 and isinstance(args[0], (list, tuple)):
            arr = args[0]
            nationID = arr[0] if len(arr) > 0 else 0
            vehicleTypeID = arr[1] if len(arr) > 1 else 0
            role = arr[2] if len(arr) > 2 else 'commander'
            tmanCostIdx = arr[3] if len(arr) > 3 else 0
        else:
            return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)

        LOG_DEBUG('CMD_RECRUIT_TANKMAN: n=%s v=%s role=%s cost=%s' % (
            nationID, vehicleTypeID, role, tmanCostIdx))

        result = shop_actions.recruitTankman(nationID, vehicleTypeID, role, tmanCostIdx)
        if result.success:
            syncResult = _buildSyncData()
            return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
        return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)

    except Exception as e:
        LOG_DEBUG('cmdRecruitTankman error: %s' % str(e))
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


@baseRequest(AccountCommands.CMD_DISMISS_TANKMAN)
def cmdDismissTankman(requestID, *args):
    """Увольнение танкиста"""
    try:
        if args and isinstance(args[0], (list, tuple)):
            tankmanID = args[0][0] if args[0] else -1
        elif args:
            tankmanID = args[0]
        else:
            tankmanID = -1

        LOG_DEBUG('CMD_DISMISS_TANKMAN: id=%s' % tankmanID)
        result = shop_actions.dismissTankman(tankmanID)
        if result.success:
            syncResult = _buildSyncData()
            return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
        return RequestResult(AccountCommands.RES_FAILURE, result.errorCode, None)

    except Exception as e:
        LOG_DEBUG('cmdDismissTankman error: %s' % str(e))
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


# ==================== УСТАНОВКА МОДУЛЕЙ ====================

@baseRequest(AccountCommands.CMD_INSTALL_VEHICLE_COMPONENT)
def cmdInstallComponent(requestID, *args):
    """Установка модуля на танк"""
    try:
        if len(args) >= 2:
            invID = args[0]
            moduleIntCD = args[1]
        elif args and isinstance(args[0], (list, tuple)):
            arr = args[0]
            invID = arr[0] if len(arr) > 0 else -1
            moduleIntCD = arr[1] if len(arr) > 1 else 0
        else:
            return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)

        LOG_DEBUG('CMD_INSTALL_COMPONENT: invID=%s intCD=%s' % (invID, moduleIntCD))

        if account_state.installModule(invID, moduleIntCD):
            syncResult = _buildSyncData()
            return RequestResult(AccountCommands.RES_SUCCESS, '', syncResult)
        return RequestResult(AccountCommands.RES_FAILURE, 'INSTALL_FAILED', None)

    except Exception as e:
        LOG_DEBUG('cmdInstallComponent error: %s' % str(e))
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


# ==================== Prebattle (заглушки) ====================

@baseRequest(AccountCommands.CMD_PRB_JOIN)
def prbJoin(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_LEAVE)
def prbLeave(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_READY)
def prbReady(requestID, *args):
    try:
        from gui.mods.mod_observer import g_instance
        if g_instance.arenaType is not None and not g_instance.isStarted:
            BigWorld.callback(0.3, g_instance.observerStart)
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_NOT_READY)
def prbNotReady(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_ASSIGN)
def prbAssign(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_SWAP_TEAM)
def prbSwapTeam(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ARENA)
def prbChangeArena(requestID, *args):
    try:
        import ArenaType
        from gui.mods.mod_observer import g_instance
        arr = args[0] if args and isinstance(args[0], (list, tuple)) else args
        if arr:
            arenaTypeID = arr[0] if isinstance(arr, (list, tuple)) else arr
            if arenaTypeID in ArenaType.g_cache:
                g_instance.arenaType = ArenaType.g_cache[arenaTypeID]
                g_instance.spaceName = g_instance.arenaType.geometryName
                g_instance.onUpdate()
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ROUND)
def prbChangeRound(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_OPEN)
def prbOpen(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_COMMENT)
def prbChangeComment(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ARENAVOIP)
def prbChangeArenaVoip(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_TEAM_READY)
def prbTeamReady(requestID, *args):
    try:
        from gui.mods.mod_observer import g_instance
        if g_instance.arenaType is not None and not g_instance.isStarted:
            BigWorld.callback(0.3, g_instance.observerStart)
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_TEAM_NOT_READY)
def prbTeamNotReady(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_KICK)
def prbKick(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_GAMEPLAYSMASK)
def prbChangeGameplaysMask(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_ACCEPT_INVITE)
def prbAcceptInvite(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_DECLINE_INVITE)
def prbDeclineInvite(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# ==================== Очередь ====================

@baseRequest(AccountCommands.CMD_ENQUEUE_RANDOM)
def enqueueRandom(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_DEQUEUE_RANDOM)
def dequeueRandom(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# ==================== Прочее ====================

@baseRequest(AccountCommands.CMD_REQ_PLAYER_INFO)
def reqPlayerInfo(requestID, *args):
    callback = packStream(requestID, (0, {}))
    if callback:
        BigWorld.callback(REQUEST_CALLBACK_TIME, callback)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_REQ_QUEUE_INFO)
def reqQueueInfo(requestID, *args):
    callback = packStream(requestID, (0, {}))
    if callback:
        BigWorld.callback(REQUEST_CALLBACK_TIME, callback)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_LOG_CLIENT_UX_EVENTS)
def logClientUxEvents(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_LOG_CLIENT_XMPP_EVENTS)
def logClientXmppEvents(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# ==================== Вспомогательные функции ====================

def _buildSyncData():
    """Строит данные для ресинхронизации после операции"""
    data = {}
    data.update(getOfflineInventory())
    data.update(getOfflineStats())
    return data