# res_mods/0.9.22.0/scripts/client/gui/mods/mod_offhangar.py
"""
Оффлайн-ангар для World of Tanks 0.9.22
Версия 7.0 - ПОЛНАЯ ФИНАЛЬНАЯ
"""

import os
import json
import time
import shutil
import zlib
import cPickle
import functools
import traceback
from collections import namedtuple

import BigWorld
import Account
import AccountCommands
import constants
import game
import nations
import items

from items import vehicles, tankmen, makeIntCompactDescrByID, getTypeOfCompactDescr
from items.vehicles import g_list, g_cache

from constants import ACCOUNT_ATTR
from predefined_hosts import g_preDefinedHosts
from connection_mgr import LOGIN_STATUS
from chat_shared import CHAT_RESPONSES

from gui.shared.gui_items import GUI_ITEM_TYPE


# =============================================================================
# КОНСТАНТЫ
# =============================================================================

OFFLINE_SERVER_ADDRES = 'wargaming.net'
OFFLINE_NICKNAME      = 'Player1'
OFFLINE_DBID          = 1
REQUEST_CALLBACK_TIME = 0.5

OFFLINE_GUI_CTX = cPickle.dumps({
    'databaseID':                   OFFLINE_DBID,
    'logUXEvents':                  True,
    'aogasStartedAt':               0,
    'sessionStartedAt':             0,
    'isAogasEnabled':               False,
    'collectUiStats':               False,
    'isLongDisconnectedFromCenter': False,
})

OFFLINE_SERVER_SETTINGS = {
    'isGoldFishEnabled':              False,
    'isVehicleRestoreEnabled':        False,
    'isFalloutQuestEnabled':          False,
    'isClubsEnabled':                 False,
    'isSandboxEnabled':               True,
    'isFortBattleDivisionsEnabled':   False,
    'isFortsEnabled':                 False,
    'isEncyclopediaEnabled':          False,
    'isStrongholdsEnabled':           False,
    'isRegularQuestEnabled':          False,
    'isSpecBattleMgrEnabled':         True,
    'isTankmanRestoreEnabled':        False,
    'wallet':                         (False, False),
    'file_server':                    {},
    'forbiddenSortiePeripheryIDs':    (),
    'newbieBattlesCount':             100,
    'roaming':                        (1, 1, [(1, 1, 2499999999, 'OFFLINE')], ()),
    'randomMapsForDemonstrator':      {},
    'spgRedesignFeatures':            {'stunEnabled': False, 'markTargetAreaEnabled': False},
    'regional_settings':              {
        'starting_day_of_a_new_week':      0,
        'starting_time_of_a_new_game_day': 0,
        'starting_time_of_a_new_day':      0,
    },
    'forbidSPGinSquads':              False,
    'forbiddenRatedBattles':          {},
    'forbiddenSortieHours':           (14,),
    'forbiddenFortDefenseHours':      (0, 1, 2, 3, 4),
    'eSportSeasonID':                 4,
    'eSportSeasonStart':              1442318400,
    'eSportSeasonFinish':             1472688000,
    'xmpp_enabled':                   False,
}

CHAT_ACTION_DATA = {
    'requestID':          None,
    'action':             None,
    'actionResponse':     CHAT_RESPONSES.connectTimeout.index(),
    'time':               0,
    'sentTime':           0,
    'channel':            0,
    'originator':         0,
    'originatorNickName': '',
    'group':              0,
    'data':               {},
    'flags':              0,
}

RequestResult = namedtuple('RequestResult', ['resultID', 'errorStr', 'data'])
BASE_REQUESTS = {}

_CMD_EQUIP_TMAN  = 600
_CMD_FREE_TMAN   = 601
_CMD_UNLOAD_TMAN = 602


# =============================================================================
# ЛОГИРОВАНИЕ
# =============================================================================

def LOG_DEBUG(msg):
    try:
        print '[OFFHANGAR] %s' % unicode(msg).encode('utf-8', 'replace')
    except:
        print '[OFFHANGAR] log'


# =============================================================================
# ХРАНИЛИЩЕ
# =============================================================================

def _getSaveDir():
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', '..', '..', '..', 'offhangar_saves'),
        os.path.join('.', 'offhangar_saves'),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        try:
            if not os.path.exists(path):
                os.makedirs(path)
            testFile = os.path.join(path, '.write_test')
            with open(testFile, 'w') as f:
                f.write('test')
            os.remove(testFile)
            return path
        except:
            continue
    return '.'


def _getSavePath():
    return os.path.join(_getSaveDir(), 'account_save.json')


def _getBackupPath():
    return os.path.join(_getSaveDir(), 'account_save.backup.json')


def _makeSerializable(obj):
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.iteritems():
            result[str(k)] = _makeSerializable(v)
        return result
    elif isinstance(obj, set):
        return {'__type__': 'set', '__data__': sorted([_makeSerializable(i) for i in obj])}
    elif isinstance(obj, frozenset):
        return {'__type__': 'frozenset', '__data__': sorted([_makeSerializable(i) for i in obj])}
    elif isinstance(obj, tuple):
        return {'__type__': 'tuple', '__data__': [_makeSerializable(i) for i in obj]}
    elif isinstance(obj, list):
        return [_makeSerializable(i) for i in obj]
    elif isinstance(obj, (bool, int, long, float, str, unicode)) or obj is None:
        return obj
    else:
        return repr(obj)


def _restoreTypes(obj):
    if isinstance(obj, dict):
        if '__type__' in obj:
            t    = obj['__type__']
            data = obj.get('__data__', [])
            if t == 'set':
                return set(_restoreTypes(i) for i in data)
            elif t == 'frozenset':
                return frozenset(_restoreTypes(i) for i in data)
            elif t == 'tuple':
                return tuple(_restoreTypes(i) for i in data)
            return None
        result = {}
        for k, v in obj.iteritems():
            if k.startswith('_save'):
                continue
            try:
                key = int(k)
            except (ValueError, TypeError):
                key = k
            result[key] = _restoreTypes(v)
        return result
    elif isinstance(obj, list):
        return [_restoreTypes(i) for i in obj]
    else:
        return obj


def storageSave(stateDict):
    try:
        savePath   = _getSavePath()
        backupPath = _getBackupPath()

        if os.path.exists(savePath):
            try:
                shutil.copy2(savePath, backupPath)
            except:
                pass

        serializable = _makeSerializable(stateDict)
        serializable['_saveTime']    = time.time()
        serializable['_saveVersion'] = 7

        tmpPath = savePath + '.tmp'
        with open(tmpPath, 'w') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

        if os.path.exists(savePath):
            os.remove(savePath)
        os.rename(tmpPath, savePath)
        return True

    except Exception as e:
        LOG_DEBUG('Save error: %s' % str(e))
        return False


def storageLoad():
    for path, name in [(_getSavePath(), 'account_save.json'),
                       (_getBackupPath(), 'account_save.backup.json')]:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r') as f:
                content = f.read()
            if not content or len(content) < 10:
                raise ValueError('File too small')
            raw = json.loads(content)
            if not isinstance(raw, dict) or '_saveVersion' not in raw:
                raise ValueError('Invalid format')
            restored = _restoreTypes(raw)
            LOG_DEBUG('Loaded from %s' % name)
            return restored
        except Exception as e:
            LOG_DEBUG('Load error (%s): %s' % (name, str(e)))
            try:
                os.remove(path)
            except:
                pass
            continue
    return None


# =============================================================================
# СОСТОЯНИЕ АККАУНТА
# =============================================================================

_accountState = {
    'credits':           100000000,
    'gold':              10000000,
    'crystal':           10000000,
    'freeXP':            10000000,
    'slots':             1000,
    'berths':            40000,
    'vehicles':          {},
    'vehicleCrew':       {},
    'tankmen':           {},
    'unlocks':           set(),
    'vehTypeXP':         {},
    'eliteVehicles':     set(),
    'modules':           {},
    '_nextVehicleID':    1,
    '_nextTankmanID':    1,
    '_initialized':      False,
    '_revision':         0,
}


def stateGet():
    return _accountState


def stateSave():
    storageSave(_accountState)


def stateInitialize(force=False):
    global _accountState

    if _accountState['_initialized'] and not force:
        return

    LOG_DEBUG('Initializing')

    saved = storageLoad()
    if saved is not None:
        _accountState.update(saved)
        _accountState['unlocks']       = set(_accountState.get('unlocks', []))
        _accountState['eliteVehicles'] = set(_accountState.get('eliteVehicles', []))
        _accountState['vehicles']      = dict(_accountState.get('vehicles', {}))
        _accountState['vehicleCrew']   = dict(_accountState.get('vehicleCrew', {}))
        _accountState['tankmen']       = dict(_accountState.get('tankmen', {}))
        _accountState['modules']       = dict(_accountState.get('modules', {}))
        _accountState['_initialized']  = True
        LOG_DEBUG('Restored: %d vehicles' % len(_accountState['vehicles']))
        return

    _createFreshState()
    _accountState['_initialized'] = True
    stateSave()
    LOG_DEBUG('Fresh state: %d vehicles' % len(_accountState['vehicles']))


def _createFreshState():
    global _accountState

    _accountState.update({
        'credits':        100000000,
        'gold':           10000000,
        'crystal':        10000000,
        'freeXP':         10000000,
        'slots':          1000,
        'berths':         40000,
        'vehicles':       {},
        'vehicleCrew':    {},
        'tankmen':        {},
        'unlocks':        set(),
        'vehTypeXP':      {},
        'eliteVehicles':  set(),
        'modules':        {},
        '_nextVehicleID': 1,
        '_nextTankmanID': 1,
        '_revision':      0,
    })

    for nationID in nations.INDICES.values():
        try:
            _unlockNationComponents(nationID)
        except:
            pass

    count = 0
    for typeID in list(g_list._VehicleList__ids.values()):
        if count >= 100:
            break
        try:
            if _addVehicleInternal(typeID, withCrew=False, skipSave=True) is not None:
                count += 1
        except:
            continue


def _unlockNationComponents(nationID):
    def safeUnlock(typeName, getter):
        try:
            return {makeIntCompactDescrByID(typeName, nationID, i)
                    for i in getter(nationID).keys()}
        except:
            return set()

    _accountState['unlocks'] |= safeUnlock('vehicleChassis', g_cache.chassis)
    _accountState['unlocks'] |= safeUnlock('vehicleEngine',  g_cache.engines)
    _accountState['unlocks'] |= safeUnlock('vehicleRadio',   g_cache.radios)
    _accountState['unlocks'] |= safeUnlock('vehicleTurret',  g_cache.turrets)
    _accountState['unlocks'] |= safeUnlock('vehicleGun',     g_cache.guns)
    _accountState['unlocks'] |= safeUnlock('vehicleFuelTank', g_cache.fuelTanks)
    _accountState['unlocks'] |= safeUnlock('shell',           g_cache.shells)

    try:
        vData = {makeIntCompactDescrByID('vehicle', nationID, i)
                 for i in g_list.getList(nationID).keys()}
        _accountState['unlocks']       |= vData
        _accountState['eliteVehicles'] |= vData
        for vIntCD in vData:
            _accountState['vehTypeXP'].setdefault(vIntCD, 0)
    except:
        pass


# =============================================================================
# ТЕХНИКА
# =============================================================================

def _addVehicleInternal(typeID, withCrew=False, skipSave=False):
    try:
        vehicle = vehicles.VehicleDescr(typeID=typeID)
        vType   = vehicle.type

        if not vType.turrets or len(vType.turrets[-1]) < 2:
            return None
        turret = vType.turrets[-1][-1]
        if not turret.guns:
            return None
        gun = turret.guns[-1]

        vehicle.installComponent(
            makeIntCompactDescrByID('vehicleChassis', vType.chassis[-1].id[0], vType.chassis[-1].id[1]))
        vehicle.installComponent(
            makeIntCompactDescrByID('vehicleEngine', vType.engines[-1].id[0], vType.engines[-1].id[1]))
        vehicle.installTurret(
            makeIntCompactDescrByID('vehicleTurret', turret.id[0], turret.id[1]),
            makeIntCompactDescrByID('vehicleGun',    gun.id[0],    gun.id[1]))
        vehicle.installComponent(
            makeIntCompactDescrByID('vehicleRadio', vType.radios[-1].id[0], vType.radios[-1].id[1]))

        invID = _accountState['_nextVehicleID']
        _accountState['_nextVehicleID'] += 1
        _accountState['vehicles'][invID]    = vehicle.makeCompactDescr()
        _accountState['vehicleCrew'][invID] = []

        if withCrew:
            nationID     = vType.id[0]
            vehTypeID    = vType.id[1]
            vehicleIntCD = makeIntCompactDescrByID('vehicle', nationID, vehTypeID)
            crewList     = []
            for crewRole in vType.crewRoles:
                role = crewRole[0] if isinstance(crewRole, (list, tuple)) else crewRole
                tid  = _createTankman(nationID, vehTypeID, role, vehicleIntCD)
                crewList.append(tid)
            if any(tid is not None for tid in crewList):
                _accountState['vehicleCrew'][invID] = crewList

        if not skipSave:
            _accountState['_revision'] += 1
            stateSave()

        return invID
    except:
        return None


def _createTankman(nationID, vehicleTypeID, role, vehicleIntCD):
    try:
        if not hasattr(tankmen, 'generateCompactDescr'):
            return None
        cd = tankmen.generateCompactDescr(
            nationID=nationID, vehicleTypeID=vehicleTypeID, role=role,
            roleLevel=100, skills=[], isFemale=False, isPremium=False,
            firstNameID=0, iconID=0,
        )
        if cd is None:
            return None
        tankmanID = _accountState['_nextTankmanID']
        _accountState['_nextTankmanID'] += 1
        _accountState['tankmen'][tankmanID] = {
            'compDescr':          cd,
            'vehicleNativeDescr': vehicleIntCD,
            'vehicleDescr':       vehicleIntCD,
        }
        return tankmanID
    except:
        return None


def _removeVehicleInternal(invID):
    if invID not in _accountState['vehicles']:
        return False
    for tankmanID in _accountState['vehicleCrew'].pop(invID, []):
        if tankmanID is not None:
            _accountState['tankmen'].pop(tankmanID, None)
    del _accountState['vehicles'][invID]
    _accountState['_revision'] += 1
    stateSave()
    return True


def _findInvIDByIntCD(intCD):
    for invID, compDescr in _accountState['vehicles'].iteritems():
        try:
            vDesc  = vehicles.VehicleDescr(compactDescr=compDescr)
            vIntCD = makeIntCompactDescrByID('vehicle', vDesc.type.id[0], vDesc.type.id[1])
            if vIntCD == intCD:
                return invID
        except:
            continue
    return None


# =============================================================================
# ВАЛЮТА
# =============================================================================

def _spendCredits(amount):
    if _accountState['credits'] >= amount:
        _accountState['credits'] -= amount
        return True
    return False

def _spendGold(amount):
    if _accountState['gold'] >= amount:
        _accountState['gold'] -= amount
        return True
    return False

def _addCredits(amount): _accountState['credits'] += amount
def _addGold(amount):    _accountState['gold']     += amount
def _addFreeXP(amount):  _accountState['freeXP']   += amount


# =============================================================================
# ЦЕНЫ
# =============================================================================

_shopPriceCache = {}

def _getShopPriceCache():
    global _shopPriceCache
    if _shopPriceCache:
        return _shopPriceCache
    try:
        shopItems = {}
        items.init(True, shopItems)
        for intCD, data in shopItems.iteritems():
            if isinstance(data, dict):
                _shopPriceCache[intCD] = (data.get('credits', 0), data.get('gold', 0))
            elif isinstance(data, (list, tuple)) and len(data) >= 2:
                _shopPriceCache[intCD] = (int(data[0]), int(data[1]))
    except:
        pass
    return _shopPriceCache


def _getBuyPrice(intCD):
    cache = _getShopPriceCache()
    if intCD in cache:
        return cache[intCD]
    try:
        if getTypeOfCompactDescr(intCD) == items.ITEM_TYPES.vehicle:
            price = getattr(vehicles.VehicleDescr(compactDescr=intCD).type, 'price', (0, 0))
            if isinstance(price, (list, tuple)) and len(price) >= 2:
                return (int(price[0]), int(price[1]))
    except:
        pass
    return (0, 0)


def _getSellPrice(intCD):
    buy = _getBuyPrice(intCD)
    return (int(buy[0] * 0.5), int(buy[1] * 0.5))


def _normalizeVehicleIntCD(intCD):
    try:
        if getTypeOfCompactDescr(intCD) == items.ITEM_TYPES.vehicle:
            return intCD
    except:
        pass
    if isinstance(intCD, (int, long)) and 0 < intCD < 10000:
        for nationID in nations.INDICES.values():
            try:
                if intCD in g_list.getList(nationID):
                    return makeIntCompactDescrByID('vehicle', nationID, intCD)
            except:
                continue
    if isinstance(intCD, (tuple, list)) and len(intCD) == 2:
        try:
            return makeIntCompactDescrByID('vehicle', intCD[0], intCD[1])
        except:
            pass
    return None


# =============================================================================
# РЕЗУЛЬТАТЫ МАГАЗИНА
# =============================================================================

class ShopResult(object):
    def __init__(self, ok, code='', message='', invID=None):
        self.ok      = ok
        self.code    = code
        self.message = message
        self.invID   = invID


# =============================================================================
# ОПЕРАЦИИ МАГАЗИНА
# =============================================================================

def shopBuyVehicle(intCD, buyShells=True, recruitCrew=False, tmanCostIdx=0):
    intCD = _normalizeVehicleIntCD(intCD)
    if intCD is None:
        return ShopResult(False, 'VEHICLE_NOT_FOUND')
    if _findInvIDByIntCD(intCD) is not None:
        return ShopResult(False, 'ALREADY_OWNED')

    buyPrice    = _getBuyPrice(intCD)
    creditsNeed = buyPrice[0]
    goldNeed    = buyPrice[1]

    TMAN_COSTS = [
        {'credits': 0,     'gold': 0},
        {'credits': 20000, 'gold': 0},
        {'credits': 0,     'gold': 200},
    ]
    if recruitCrew:
        try:
            crewCount = len(vehicles.VehicleDescr(compactDescr=intCD).type.crewRoles)
        except:
            crewCount = 4
        cost = TMAN_COSTS[max(0, min(tmanCostIdx, 2))]
        creditsNeed += cost['credits'] * crewCount
        goldNeed    += cost['gold']    * crewCount

    if creditsNeed > 0 and _accountState['credits'] < creditsNeed:
        return ShopResult(False, 'NOT_ENOUGH_CREDITS')
    if goldNeed > 0 and _accountState['gold'] < goldNeed:
        return ShopResult(False, 'NOT_ENOUGH_GOLD')

    if creditsNeed > 0: _spendCredits(creditsNeed)
    if goldNeed    > 0: _spendGold(goldNeed)

    try:
        typeID = vehicles.VehicleDescr(compactDescr=intCD).type.id
    except Exception as e:
        _addCredits(creditsNeed)
        _addGold(goldNeed)
        return ShopResult(False, 'BAD_DESCR', str(e))

    invID = _addVehicleInternal(typeID, withCrew=recruitCrew)
    if invID is None:
        _addCredits(creditsNeed)
        _addGold(goldNeed)
        return ShopResult(False, 'ADD_FAILED')

    stateSave()
    LOG_DEBUG('Bought: invID=%d intCD=%d' % (invID, intCD))
    return ShopResult(True, invID=invID)


def shopSellVehicle(invID):
    compDescr = _accountState['vehicles'].get(invID)
    if compDescr is None:
        return ShopResult(False, 'NOT_FOUND')
    try:
        vDesc = vehicles.VehicleDescr(compactDescr=compDescr)
        sell  = _getSellPrice(
            makeIntCompactDescrByID('vehicle', vDesc.type.id[0], vDesc.type.id[1]))
    except:
        sell = (0, 0)
    if not _removeVehicleInternal(invID):
        return ShopResult(False, 'REMOVE_FAILED')
    if sell[0] > 0: _addCredits(sell[0])
    if sell[1] > 0: _addGold(sell[1])
    stateSave()
    LOG_DEBUG('Sold: invID=%d' % invID)
    return ShopResult(True, invID=invID)


def shopBuySlot():
    _accountState['slots'] += 1
    _accountState['_revision'] += 1
    stateSave()
    return ShopResult(True)


def shopBuyBerths(count=16):
    _accountState['berths'] += count
    _accountState['_revision'] += 1
    stateSave()
    return ShopResult(True)


def shopExchangeGoldToCredits(goldAmount):
    if not _spendGold(goldAmount):
        return ShopResult(False, 'NOT_ENOUGH_GOLD')
    _addCredits(goldAmount * 400)
    _accountState['_revision'] += 1
    stateSave()
    return ShopResult(True)


# =============================================================================
# ЭКИПАЖ
# =============================================================================

def recruitTankmanForVehicle(invID, slotIdx, tmanCostIdx=0):
    try:
        compDescr = _accountState['vehicles'].get(invID)
        if compDescr is None:
            return ShopResult(False, 'VEHICLE_NOT_FOUND')

        vDesc        = vehicles.VehicleDescr(compactDescr=compDescr)
        vType        = vDesc.type
        nationID     = vType.id[0]
        vehTypeID    = vType.id[1]
        vehicleIntCD = makeIntCompactDescrByID('vehicle', nationID, vehTypeID)

        if slotIdx < 0 or slotIdx >= len(vType.crewRoles):
            return ShopResult(False, 'BAD_SLOT_IDX')

        crewRole = vType.crewRoles[slotIdx]
        role     = crewRole[0] if isinstance(crewRole, (list, tuple)) else crewRole

        TMAN_COSTS = [
            {'credits': 0,     'gold': 0},
            {'credits': 20000, 'gold': 0},
            {'credits': 0,     'gold': 200},
        ]
        cost = TMAN_COSTS[max(0, min(tmanCostIdx, 2))]

        if cost['credits'] > 0 and _accountState['credits'] < cost['credits']:
            return ShopResult(False, 'NOT_ENOUGH_CREDITS')
        if cost['gold'] > 0 and _accountState['gold'] < cost['gold']:
            return ShopResult(False, 'NOT_ENOUGH_GOLD')

        if cost['credits'] > 0: _spendCredits(cost['credits'])
        if cost['gold']    > 0: _spendGold(cost['gold'])

        tankmanID = _createTankman(nationID, vehTypeID, role, vehicleIntCD)
        if tankmanID is None:
            if cost['credits'] > 0: _addCredits(cost['credits'])
            if cost['gold']    > 0: _addGold(cost['gold'])
            return ShopResult(False, 'RECRUIT_FAILED')

        if invID not in _accountState['vehicleCrew']:
            _accountState['vehicleCrew'][invID] = [None] * len(vType.crewRoles)

        crew = _accountState['vehicleCrew'][invID]
        while len(crew) <= slotIdx:
            crew.append(None)

        oldTID = crew[slotIdx]
        if oldTID is not None:
            _accountState['tankmen'].pop(oldTID, None)

        crew[slotIdx] = tankmanID
        _accountState['_revision'] += 1
        stateSave()
        LOG_DEBUG('Recruited tman=%d slot=%d' % (tankmanID, slotIdx))
        return ShopResult(True, invID=tankmanID)

    except Exception as e:
        LOG_DEBUG('Recruit error: %s' % str(e))
        return ShopResult(False, 'INTERNAL_ERROR', str(e))


def dismissTankman(tankmanID):
    if tankmanID not in _accountState['tankmen']:
        return ShopResult(False, 'NOT_FOUND')
    del _accountState['tankmen'][tankmanID]
    for crew in _accountState['vehicleCrew'].itervalues():
        for i, tid in enumerate(crew):
            if tid == tankmanID:
                crew[i] = None
    _accountState['_revision'] += 1
    stateSave()
    return ShopResult(True)


def unloadTankman(invID, slotIdx):
    crew = _accountState['vehicleCrew'].get(invID)
    if crew is None or slotIdx < 0 or slotIdx >= len(crew):
        return ShopResult(False, 'BAD_ARGS')
    tankmanID    = crew[slotIdx]
    crew[slotIdx] = None
    _accountState['_revision'] += 1
    stateSave()
    return ShopResult(True, invID=tankmanID)


# =============================================================================
# СИНХРОНИЗАЦИЯ
# =============================================================================

def buildInventory():
    stateInitialize()
    st   = _accountState
    data = {i: {} for i in GUI_ITEM_TYPE.ALL()}
    data[GUI_ITEM_TYPE.VEHICLE] = {
        'repair':                  {},
        'lastCrew':                dict(st['vehicleCrew']),
        'settings':                {},
        'compDescr':               dict(st['vehicles']),
        'eqs':                     {},
        'shells':                  {},
        'customizationExpiryTime': {},
        'lock':                    {},
        'shellsLayout':            {},
        'vehicle':                 {},
    }
    return {'inventory': data}


def buildStats():
    stateInitialize()
    st    = _accountState
    attrs = 0
    for field in dir(ACCOUNT_ATTR):
        val = getattr(ACCOUNT_ATTR, field, None)
        if isinstance(val, (int, long)):
            attrs |= val
    return {
        'stats': {
            'crystalExchangeRate':        200,
            'berths':                     st['berths'],
            'accOnline':                  0,
            'autoBanTime':                0,
            'gold':                       st['gold'],
            'crystal':                    st['crystal'],
            'isFinPswdVerified':          True,
            'finPswdAttemptsLeft':         0,
            'denunciationsLeft':           0,
            'freeVehiclesLeft':            0,
            'refSystem':                  {'referrals': {}},
            'slots':                      st['slots'],
            'battlesTillCaptcha':          0,
            'hasFinPassword':             True,
            'clanInfo':                   (None, None, 0, 0, 0),
            'unlocks':                    st['unlocks'],
            'mayConsumeWalletResources':   True,
            'freeTMenLeft':                0,
            'vehicleSellsLeft':            0,
            'SPA':                        {'/common/goldfish_bonus_applied/': u'1'},
            'vehTypeXP':                  st['vehTypeXP'],
            'unitAcceptDeadline':          0,
            'globalVehicleLocks':          {},
            'freeXP':                     st['freeXP'],
            'captchaTriesLeft':            0,
            'fortResource':                0,
            'premiumExpiryTime':           8000,
            'tkillIsSuspected':           False,
            'credits':                    st['credits'],
            'vehTypeLocks':                {},
            'dailyPlayHours':             [0],
            'globalRating':                9000,
            'restrictions':                {},
            'oldVehInvID':                 0,
            'accOffline':                  0,
            'dossier':                     '',
            'multipliedXPVehs':            {},
            'tutorialsCompleted':          33553532,
            'eliteVehicles':              st['eliteVehicles'],
            'playLimits':                 ((0, ''), (0, '')),
            'clanDBID':                    0,
            'attrs':                       attrs,
            'tankmen':                     st['tankmen'],
            'winXPFactorMode':             0,
        }
    }


def buildShop():
    try:
        shopItems = {}
        items.init(True, shopItems)
    except:
        shopItems = {}
    return {
        'crystalExchangeRate':                 200,
        'camouflageCost':                      {0: (250, True), 7: (25000, False), 30: (100000, False)},
        'goodies':                             {'prices': {}, 'notInShop': set(), 'goodies': {}},
        'berthsPrices':                        (16, 16, [300]),
        'femalePassportChangeCost':             50,
        'freeXPConversion':                    (100000, 0.1),
        'dropSkillsCost': {
            0: {'xpReuseFraction': 0.5,  'gold': 0,  'credits': 0},
            1: {'xpReuseFraction': 0.75, 'gold': 0,  'credits': 20000},
            2: {'xpReuseFraction': 1.0,  'gold': 10, 'credits': 1000},
        },
        'refSystem': {
            'maxNumberOfReferrals': 50,
            'posByXPinTeam':        10,
            'maxReferralXPPool':    350000,
            'periods':              [(24, 3.0), (168, 2.0), (876000, 1.5)],
        },
        'playerEmblemCost':                    {0: (15, True), 7: (1500, False), 30: (6000, False)},
        'premiumCost':                         {1: 1, 3: 1, 7: 1, 30: 1, 180: 1, 360: 1},
        'winXPFactorMode':                     0,
        'sellPriceModif':                      0.75,
        'passportChangeCost':                  50,
        'exchangeRateForShellsAndEqs':         400,
        'exchangeRate':                        400,
        'tankmanCost': (
            {'isPremium': False, 'baseRoleLoss': 0.2, 'gold': 0,
             'credits': 0,     'classChangeRoleLoss': 0.2, 'roleLevel': 50},
            {'isPremium': False, 'baseRoleLoss': 0.1, 'gold': 0,
             'credits': 20000, 'classChangeRoleLoss': 0.1, 'roleLevel': 75},
            {'isPremium': True,  'baseRoleLoss': 0.0, 'gold': 200,
             'credits': 0,     'classChangeRoleLoss': 0.0, 'roleLevel': 100},
        ),
        'paidRemovalCost':                     0,
        'dailyXPFactor':                       100,
        'changeRoleCost':                      500,
        'isEnabledBuyingGoldShellsForCredits':  False,
        'items':                               shopItems,
        'slotsPrices':                         (9, [1]),
        'freeXPToTManXPRate':                  10,
        'defaults': {
            'items':             shopItems,
            'freeXPToTManXPRate': 0,
            'goodies':           {'prices': {}},
        },
        'sellPriceFactor':                     0.5,
        'isEnabledBuyingGoldEqsForCredits':     False,
        'playerInscriptionCost': {
            0:         (15,   True),
            7:         (1500, False),
            30:        (6000, False),
            'nations': {},
        },
    }


def buildQuestsProgress():
    return {
        'tokens': {},
        'potapovQuests': {
            'compDescr': '',
            'regular': {
                'tiles':     set(),
                'rewards':   {},
                'compDescr': '',
                'selected':  set([1, 17, 31, 46, 61]),
                'lastIDs':   {},
                'slots':     2,
            },
            'fallout': {
                'tiles':     set(),
                'rewards':   {},
                'compDescr': '',
                'selected':  set([301, 401]),
                'lastIDs':   {},
                'slots':     2,
            },
        },
        'quests': {},
    }


def buildSyncData(revision=0):
    stateInitialize()
    st  = _accountState
    rev = st.get('_revision', revision)
    data = {'rev': rev + 1, 'prevRev': rev}
    data.update(buildInventory())
    data.update(buildStats())
    data.update(buildQuestsProgress())
    st['_revision'] = rev + 1
    return data


def packStream(requestID, data):
    try:
        packed = zlib.compress(cPickle.dumps(data))
        desc   = cPickle.dumps((len(packed), zlib.crc32(packed)))
        return functools.partial(game.onStreamComplete, requestID, desc, packed)
    except Exception as e:
        LOG_DEBUG('Stream error: %s' % str(e))
        return None


def _syncResult():
    return buildSyncData()


def _extractFirstInt(args):
    if not args:
        return None
    first = args[0]
    if isinstance(first, (int, long)):
        return first
    if isinstance(first, (list, tuple)) and first:
        try:
            return int(first[0])
        except:
            return None
    try:
        return int(first)
    except:
        return None


# =============================================================================
# FAKE SERVER
# =============================================================================

class FakeServer(object):
    def __init__(self, name='Server', isMuted=False):
        object.__setattr__(self, '_FakeServer__name',    name)
        object.__setattr__(self, '_FakeServer__isMuted', isMuted)

    def __getattr__(self, name):
        return FakeServer(
            name='%s.%s' % (object.__getattribute__(self, '_FakeServer__name'), name),
            isMuted=object.__getattribute__(self, '_FakeServer__isMuted'),
        )

    def __call__(self, *args, **kwargs):
        pass

    def chatCommandFromClient(self, requestID, action, channelID,
                              int64Arg, int16Arg, stringArg1, stringArg2):
        try:
            data = CHAT_ACTION_DATA.copy()
            data['requestID'] = requestID
            data['action']    = action
            BigWorld.player().onChatAction(data)
        except:
            pass

    def doCmdStr(self, requestID, cmd, s):
        self._doCmd(requestID, cmd, s)

    def doCmdIntStr(self, requestID, cmd, i, s):
        self._doCmd(requestID, cmd, i, s)

    def doCmdInt3(self, requestID, cmd, i1, i2, i3):
        self._doCmd(requestID, cmd, i1, i2, i3)

    def doCmdInt4(self, requestID, cmd, i1, i2, i3, i4):
        self._doCmd(requestID, cmd, i1, i2, i3, i4)

    def doCmdInt2Str(self, requestID, cmd, i1, i2, s):
        self._doCmd(requestID, cmd, i1, i2, s)

    def doCmdIntArr(self, requestID, cmd, arr):
        self._doCmd(requestID, cmd, arr)

    def doCmdIntArrStrArr(self, requestID, cmd, iA, sA):
        self._doCmd(requestID, cmd, iA, sA)

    def prb_createTrainingRoom(self, arenaTypeID, roundLength, isPrivate, comment):
        try:
            import ArenaType
            from constants import ARENA_GUI_TYPE
            from gui.mods.mod_observer import g_instance
            g_instance.arenaType    = ArenaType.g_cache[arenaTypeID]
            g_instance.spaceName    = g_instance.arenaType.geometryName
            g_instance.arenaGuiType = ARENA_GUI_TYPE.TRAINING
            BigWorld.callback(0.3, g_instance.observerStart)
        except:
            pass

    def prb_join(self, *a):              pass
    def prb_leave(self, *a):             pass
    def prb_notReady(self, *a):          pass
    def prb_assign(self, *a):            pass
    def prb_requestPlayerData(self, *a): pass
    def prb_kick(self, *a):              pass
    def prb_swap(self, *a):              pass
    def prb_changeSettings(self, *a):    pass
    def prb_createSquad(self, *a):       pass
    def prb_sendInvites(self, *a):       pass
    def prb_destroyTrainingRoom(self, *a): pass

    def prb_ready(self, *a):
        try:
            from gui.mods.mod_observer import g_instance
            if g_instance.arenaType is not None and not g_instance.isStarted:
                BigWorld.callback(0.1, g_instance.observerStart)
        except:
            pass

    def prb_startBattle(self, *a):
        try:
            from gui.mods.mod_observer import g_instance
            if not g_instance.isStarted:
                BigWorld.callback(0.1, g_instance.observerStart)
        except:
            pass

    def prb_changeArena(self, arenaTypeID, *a):
        try:
            import ArenaType
            from gui.mods.mod_observer import g_instance
            if arenaTypeID in ArenaType.g_cache:
                g_instance.arenaType = ArenaType.g_cache[arenaTypeID]
                g_instance.spaceName = g_instance.arenaType.geometryName
                g_instance.onUpdate()
        except:
            pass

    def _doCmd(self, requestID, cmd, *args):
        try:
            handler = BASE_REQUESTS.get(cmd)
            if handler:
                requestID, resultID, errorStr, ext = handler(requestID, *args)
            else:
                LOG_DEBUG('Unknown cmd: %s' % cmd)
                requestID, resultID, errorStr, ext = (
                    requestID, AccountCommands.RES_FAILURE, '', None)

            player = BigWorld.player()
            if ext is not None:
                cb = functools.partial(
                    player.onCmdResponseExt,
                    requestID, resultID, errorStr, cPickle.dumps(ext))
            else:
                cb = functools.partial(
                    player.onCmdResponse,
                    requestID, resultID, errorStr)
            BigWorld.callback(0.0, cb)
        except Exception as e:
            LOG_DEBUG('doCmd error: %s' % str(e))


# =============================================================================
# ДЕКОРАТОР
# =============================================================================

def baseRequest(cmdID):
    def wrapper(func):
        def requester(requestID, *args):
            try:
                result = func(requestID, *args)
                return requestID, result.resultID, result.errorStr, result.data
            except Exception as e:
                LOG_DEBUG('Request error: %s' % str(e))
                return requestID, AccountCommands.RES_FAILURE, str(e), None
        BASE_REQUESTS[cmdID] = requester
        return func
    return wrapper


# =============================================================================
# КОМАНДЫ: СИНХРОНИЗАЦИЯ
# =============================================================================

@baseRequest(AccountCommands.CMD_COMPLETE_TUTORIAL)
def cmdCompleteTutorial(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_SYNC_DATA)
def cmdSyncData(requestID, revision, crc, _):
    stateInitialize()
    return RequestResult(AccountCommands.RES_SUCCESS, '', buildSyncData(revision))


@baseRequest(AccountCommands.CMD_SYNC_SHOP)
def cmdSyncShop(requestID, revision, dataLen, dataCrc):
    data = {'rev': revision + 1, 'prevRev': revision}
    data.update(buildShop())
    cb = packStream(requestID, data)
    if cb:
        BigWorld.callback(REQUEST_CALLBACK_TIME, cb)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_SYNC_DOSSIERS)
def cmdSyncDossiers(requestID, revision, maxChangeTime, _):
    cb = packStream(requestID, (revision + 1, []))
    if cb:
        BigWorld.callback(REQUEST_CALLBACK_TIME, cb)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


# =============================================================================
# КОМАНДЫ: ПОКУПКИ
# =============================================================================

@baseRequest(301)
def cmdBuyVehicle301(requestID, *args):
    try:
        intCD       = None
        buyShells   = True
        recruitCrew = False
        tmanCostIdx = 0

        if len(args) >= 1:
            if isinstance(args[0], (int, long)):
                intCD = args[0]
            elif isinstance(args[0], (list, tuple)) and args[0]:
                arr = args[0]
                intCD = arr[0]
                if len(arr) > 1: buyShells   = bool(arr[1])
                if len(arr) > 2: recruitCrew = bool(arr[2])
                if len(arr) > 3: tmanCostIdx = int(arr[3])

        if intCD is None:
            return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)

        LOG_DEBUG('Buy: intCD=%s' % intCD)
        result = shopBuyVehicle(intCD, buyShells, recruitCrew, tmanCostIdx)

        if result.ok:
            return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
        LOG_DEBUG('Buy failed: %s' % result.code)
        return RequestResult(AccountCommands.RES_FAILURE, result.code, None)

    except Exception as e:
        LOG_DEBUG('CMD_301 error: %s' % str(e))
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


@baseRequest(AccountCommands.CMD_SELL_VEHICLE)
def cmdSellVehicle(requestID, *args):
    invID = _extractFirstInt(args)
    if invID is None:
        return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)
    result = shopSellVehicle(invID)
    if result.ok:
        return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
    return RequestResult(AccountCommands.RES_FAILURE, result.code, None)


@baseRequest(AccountCommands.CMD_BUY_SLOT)
def cmdBuySlot(requestID, *args):
    result = shopBuySlot()
    if result.ok:
        return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
    return RequestResult(AccountCommands.RES_FAILURE, result.code, None)


@baseRequest(AccountCommands.CMD_BUY_BERTHS)
def cmdBuyBerths(requestID, *args):
    result = shopBuyBerths()
    if result.ok:
        return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
    return RequestResult(AccountCommands.RES_FAILURE, result.code, None)


@baseRequest(AccountCommands.CMD_EXCHANGE)
def cmdExchange(requestID, goldAmount, *args):
    result = shopExchangeGoldToCredits(int(goldAmount))
    if result.ok:
        return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
    return RequestResult(AccountCommands.RES_FAILURE, result.code, None)


# =============================================================================
# КОМАНДЫ: ЭКИПАЖ
# =============================================================================

@baseRequest(_CMD_EQUIP_TMAN)
def cmdEquipTankman(requestID, *args):
    try:
        if len(args) >= 3:
            invID, slotIdx, tmanCostIdx = int(args[0]), int(args[1]), int(args[2])
        elif args and isinstance(args[0], (list, tuple)):
            arr         = args[0]
            invID       = int(arr[0]) if len(arr) > 0 else -1
            slotIdx     = int(arr[1]) if len(arr) > 1 else 0
            tmanCostIdx = int(arr[2]) if len(arr) > 2 else 0
        else:
            return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)
        result = recruitTankmanForVehicle(invID, slotIdx, tmanCostIdx)
        if result.ok:
            return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
        return RequestResult(AccountCommands.RES_FAILURE, result.code, None)
    except Exception as e:
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


@baseRequest(_CMD_FREE_TMAN)
def cmdFreeTankman(requestID, *args):
    tankmanID = _extractFirstInt(args)
    if tankmanID is None:
        return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)
    result = dismissTankman(tankmanID)
    if result.ok:
        return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
    return RequestResult(AccountCommands.RES_FAILURE, result.code, None)


@baseRequest(_CMD_UNLOAD_TMAN)
def cmdUnloadTankman(requestID, *args):
    try:
        if len(args) >= 2:
            invID, slotIdx = int(args[0]), int(args[1])
        elif args and isinstance(args[0], (list, tuple)):
            arr     = args[0]
            invID   = int(arr[0]) if len(arr) > 0 else -1
            slotIdx = int(arr[1]) if len(arr) > 1 else 0
        else:
            return RequestResult(AccountCommands.RES_FAILURE, 'BAD_ARGS', None)
        result = unloadTankman(invID, slotIdx)
        if result.ok:
            return RequestResult(AccountCommands.RES_SUCCESS, '', _syncResult())
        return RequestResult(AccountCommands.RES_FAILURE, result.code, None)
    except Exception as e:
        return RequestResult(AccountCommands.RES_FAILURE, 'INTERNAL_ERROR', None)


# =============================================================================
# КОМАНДЫ: СЕРВЕР
# =============================================================================

@baseRequest(AccountCommands.CMD_REQ_SERVER_STATS)
def cmdReqServerStats(requestID, *args):
    cb = packStream(requestID, (0, {}))
    if cb:
        BigWorld.callback(REQUEST_CALLBACK_TIME, cb)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_REQ_PREBATTLES)
def cmdReqPrebattles(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_REQ_PREBATTLES_BY_CREATOR)
def cmdReqPrebattlesByCreator(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_REQ_PREBATTLE_ROSTER)
def cmdReqPrebattleRoster(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_REQ_PLAYER_INFO)
def cmdReqPlayerInfo(requestID, *args):
    cb = packStream(requestID, (0, {}))
    if cb:
        BigWorld.callback(REQUEST_CALLBACK_TIME, cb)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


@baseRequest(AccountCommands.CMD_REQ_QUEUE_INFO)
def cmdReqQueueInfo(requestID, *args):
    cb = packStream(requestID, (0, {}))
    if cb:
        BigWorld.callback(REQUEST_CALLBACK_TIME, cb)
    return RequestResult(AccountCommands.RES_STREAM, '', None)


# =============================================================================
# КОМАНДЫ: НАСТРОЙКИ
# =============================================================================

@baseRequest(AccountCommands.CMD_ADD_INT_USER_SETTINGS)
def cmdAddIntUserSettings(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_DEL_INT_USER_SETTINGS)
def cmdDelIntUserSettings(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_GET_AVATAR_SYNC)
def cmdGetAvatarSync(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_LOG_CLIENT_UX_EVENTS)
def cmdLogClientUxEvents(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


@baseRequest(AccountCommands.CMD_LOG_CLIENT_XMPP_EVENTS)
def cmdLogClientXmppEvents(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# =============================================================================
# КОМАНДЫ: PREBATTLE
# =============================================================================

@baseRequest(AccountCommands.CMD_PRB_JOIN)
def cmdPrbJoin(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_LEAVE)
def cmdPrbLeave(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_READY)
def cmdPrbReady(requestID, *args):
    try:
        from gui.mods.mod_observer import g_instance
        if g_instance.arenaType is not None and not g_instance.isStarted:
            BigWorld.callback(0.3, g_instance.observerStart)
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_NOT_READY)
def cmdPrbNotReady(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_ASSIGN)
def cmdPrbAssign(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_SWAP_TEAM)
def cmdPrbSwapTeam(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ARENA)
def cmdPrbChArena(requestID, *args):
    try:
        import ArenaType
        from gui.mods.mod_observer import g_instance
        arenaTypeID = _extractFirstInt(args)
        if arenaTypeID and arenaTypeID in ArenaType.g_cache:
            g_instance.arenaType = ArenaType.g_cache[arenaTypeID]
            g_instance.spaceName = g_instance.arenaType.geometryName
            g_instance.onUpdate()
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ROUND)
def cmdPrbChRound(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_OPEN)
def cmdPrbOpen(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_COMMENT)
def cmdPrbChComment(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_ARENAVOIP)
def cmdPrbChArenaVoip(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_TEAM_READY)
def cmdPrbTeamReady(requestID, *args):
    try:
        from gui.mods.mod_observer import g_instance
        if g_instance.arenaType is not None and not g_instance.isStarted:
            BigWorld.callback(0.3, g_instance.observerStart)
    except:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_TEAM_NOT_READY)
def cmdPrbTeamNotReady(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_KICK)
def cmdPrbKick(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_CH_GAMEPLAYSMASK)
def cmdPrbChGameplaysMask(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_ACCEPT_INVITE)
def cmdPrbAcceptInvite(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_PRB_DECLINE_INVITE)
def cmdPrbDeclineInvite(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# =============================================================================
# КОМАНДЫ: ОЧЕРЕДЬ
# =============================================================================

@baseRequest(AccountCommands.CMD_ENQUEUE_RANDOM)
def cmdEnqueueRandom(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})

@baseRequest(AccountCommands.CMD_DEQUEUE_RANDOM)
def cmdDequeueRandom(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', {})


# =============================================================================
# ПАТЧИ ДЛЯ OFFLINE
# =============================================================================

def _isOffline():
    try:
        player = BigWorld.player()
        return player is not None and getattr(player, 'isOffline', False)
    except:
        return False


def _patchSyncController():
    try:
        from account_helpers.SyncController import SyncController
        _orig = SyncController.request
        def _new(self, *args, **kwargs):
            if _isOffline(): return
            return _orig(self, *args, **kwargs)
        SyncController.request = _new
        LOG_DEBUG('SyncController patched')
    except: pass

def _patchClientChat():
    try:
        import ClientChat
        _orig = ClientChat.ClientChat._ClientChat__baseChatCommand

        def _new(self, *args, **kwargs):
            if _isOffline():
                return
            return _orig(self, *args, **kwargs)

        ClientChat.ClientChat._ClientChat__baseChatCommand = _new
        LOG_DEBUG('ClientChat patched')
    except Exception as e:
        LOG_DEBUG('ClientChat patch failed: %s' % str(e))


def _patchUsersManager():
    try:
        from messenger.proto.bw.UsersManager import UsersManager
        _orig = UsersManager.requestFriendStatus

        def _new(self, *args, **kwargs):
            if _isOffline():
                return
            return _orig(self, *args, **kwargs)

        UsersManager.requestFriendStatus = _new
        LOG_DEBUG('UsersManager patched')
    except Exception as e:
        LOG_DEBUG('UsersManager patch failed: %s' % str(e))


def _patchMessenger():
    # В 0.9.22 чат часто вызывает зависание, если его не "заглушить" полностью
    try:
        from messenger.MessengerEntry import MessengerEntry
        def _empty_method(*args, **kwargs): return None
        MessengerEntry.start = _empty_method
        MessengerEntry.stop = _empty_method
        LOG_DEBUG('MessengerEntry stubbed')
    except:
        LOG_DEBUG('MessengerEntry patch failed')

    try:
        from messenger.proto.bw_chat2.MessengerController import MessengerController
        MessengerController.connect = lambda *args, **kwargs: None
        LOG_DEBUG('BwChat2 patched')
    except: pass


def _patchBwChat():
    try:
        from messenger.proto.bw_chat2 import MessengerController as _mc
        _orig = _mc.MessengerController.connect

        def _new(self, *args, **kwargs):
            if _isOffline():
                return
            return _orig(self, *args, **kwargs)

        _mc.MessengerController.connect = _new
        LOG_DEBUG('BwChat2 patched')
    except Exception as e:
        LOG_DEBUG('BwChat2 patch failed: %s' % str(e))


def _patchXMPP():
    try:
        from messenger.proto.xmpp import XmppChatController as _xc
        _orig = _xc.XmppChatController.connect

        def _new(self, *args, **kwargs):
            if _isOffline():
                return
            return _orig(self, *args, **kwargs)

        _xc.XmppChatController.connect = _new
        LOG_DEBUG('XMPP patched')
    except Exception as e:
        LOG_DEBUG('XMPP patch failed: %s' % str(e))


def _patchVoip():
    try:
        from messenger.proto.bw_chat2.VOIPChatController import VOIPChatController
        _orig = VOIPChatController.initialize

        def _new(self, *args, **kwargs):
            if _isOffline():
                return
            return _orig(self, *args, **kwargs)

        VOIPChatController.initialize = _new
        LOG_DEBUG('VOIP patched')
    except Exception as e:
        LOG_DEBUG('VOIP patch failed: %s' % str(e))


# Применяем все патчи
_patchSyncController()
_patchClientChat()
_patchUsersManager()
_patchMessenger() 


# =============================================================================
# ПЕРЕОПРЕДЕЛЕНИЯ ACCOUNT
# =============================================================================

_original_Account_init = Account.PlayerAccount.__init__

def _new_Account_init(self):
    LOG_DEBUG('Init')
    self.isOffline = not hasattr(self, 'name')

    if self.isOffline:
        LOG_DEBUG('Offline mode')
        constants.IS_DEVELOPMENT = True
        self.fakeServer = FakeServer()
        setattr(self, *Account._CLIENT_SERVER_VERSION)
        self.name = OFFLINE_NICKNAME
        self.initialServerSettings = OFFLINE_SERVER_SETTINGS

    _original_Account_init(self)

    if self.isOffline:
        BigWorld.player(self)
        stateInitialize()
        LOG_DEBUG('Account ready')


Account.PlayerAccount.__init__ = _new_Account_init


_original_Account_getattr = getattr(Account.PlayerAccount, '__getattr__', None)

def _new_Account_getattr(self, name):
    if name in ('cell', 'base', 'server') and getattr(self, 'isOffline', False):
        return object.__getattribute__(self, 'fakeServer')
    if _original_Account_getattr:
        return _original_Account_getattr(self, name)
    raise AttributeError("'%s' has no attribute '%s'" % (
        self.__class__.__name__, name))


Account.PlayerAccount.__getattr__ = _new_Account_getattr


_original_Account_onBecomePlayer = Account.PlayerAccount.onBecomePlayer

def _new_Account_onBecomePlayer(self):
    LOG_DEBUG('onBecomePlayer')
    if not getattr(self, 'isOffline', False):
        _original_Account_onBecomePlayer(self)
        return

    # Вызываем оригинал — все внутренние падения перехвачены патчами
    try:
        _original_Account_onBecomePlayer(self)
    except Exception as e:
        LOG_DEBUG('onBecomePlayer inner (safe): %s' % str(e))

    # Показываем GUI с задержкой
    BigWorld.callback(0.5, functools.partial(_showOfflineGUI, self))


def _showOfflineGUI(account):
    try:
        LOG_DEBUG('ShowGUI')
        account.showGUI(OFFLINE_GUI_CTX)
    except Exception as e:
        LOG_DEBUG('ShowGUI error: %s' % str(e))


Account.PlayerAccount.onBecomePlayer = _new_Account_onBecomePlayer


# =============================================================================
# BigWorld.connect
# =============================================================================

_original_BigWorld_connect = BigWorld.connect

def _new_BigWorld_connect(server, loginParams, progressFn):
    if server == OFFLINE_SERVER_ADDRES:
        LOG_DEBUG('Offline connect')
        progressFn(1, LOGIN_STATUS.LOGGED_ON, '{}')
        BigWorld.createEntity(
            'Account', BigWorld.createSpace(), 0, (0, 0, 0), (0, 0, 0), {})
    else:
        _original_BigWorld_connect(server, loginParams, progressFn)


BigWorld.connect = _new_BigWorld_connect


# =============================================================================
# АВТОСОХРАНЕНИЕ
# =============================================================================

try:
    _original_game_fini = game.fini

    def _new_game_fini():
        LOG_DEBUG('Save on exit')
        try:
            stateSave()
        except:
            pass
        _original_game_fini()

    game.fini = _new_game_fini
except:
    pass


# =============================================================================
# ХОСТ
# =============================================================================

try:
    g_preDefinedHosts._hosts.append(
        g_preDefinedHosts._makeHostItem(
            OFFLINE_SERVER_ADDRES,
            OFFLINE_SERVER_ADDRES,
            OFFLINE_SERVER_ADDRES,
        )
    )
except:
    pass


LOG_DEBUG('=== v7.0 LOADED ===')