import json
import nations
import items

from helpers import dependency
from constants import ACCOUNT_ATTR

from items import utils, vehicles, tankmen, getTypeOfCompactDescr, makeIntCompactDescrByID
from items.vehicles import g_list, g_cache
from items.vehicles import VehicleDescr

from gui.shared.gui_items import GUI_ITEM_TYPE
from gui.shared.gui_items.Vehicle import Vehicle

from skeletons.gui.shared import IItemsCache

from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.utils import *
from gui.mods.offhangar._constants import *


def _makeTankmanCompDescr(nationID, vehicleTypeID, role, roleLevel=100):
    """Создаёт валидный compact descriptor для танкиста"""
    try:
        tDescr = tankmen.TankmanDescr(
            nationID=nationID,
            vehicleTypeID=vehicleTypeID,
            vehicleNationID=nationID,
            role=role,
            firstNameID=0,
            lastNameID=0,
            iconID=0,
            isPremium=False,
            roleLevel=roleLevel,
            skills=[],
            isFemale=False
        )
        return tDescr.makeCompactDescr()
    except Exception as e:
        LOG_DEBUG('_makeTankmanCompDescr error nation=%d veh=%d role=%s: %s' % (
            nationID, vehicleTypeID, role, str(e)))
        return None


@dependency.replace_none_kwargs(itemsCache=IItemsCache)
def getOfflineInventory(tankmenMapping=None, itemsCache=None):
    """Создание оффлайн инвентаря с танками и экипажами"""
    try:
        LOG_DEBUG('Creating offline inventory')
        data = {i: {} for i in GUI_ITEM_TYPE.ALL()}

        compDescr = {}
        vehicleIdx = 1
        vehicleTankmen = {}
        tankmenID = 1
        vehicle_count = 0

        for value in list(g_list._VehicleList__ids.values())[:100]:
            try:
                vehicle = vehicles.VehicleDescr(typeID=value)
                intCompDescr = vehicles.makeIntCompactDescrByID('vehicle', *value)

                vDesc = vehicle
                vType = vDesc.type

                if len(vType.turrets) == 0 or len(vType.turrets[-1]) <= 1:
                    continue

                turretv = vType.turrets[-1][-1]
                if len(turretv.guns) == 0:
                    continue

                gunv = turretv.guns[-1]

                gunIDv     = makeIntCompactDescrByID('vehicleGun',    gunv.id[0],              gunv.id[1])
                turretIDv  = makeIntCompactDescrByID('vehicleTurret', turretv.id[0],           turretv.id[1])
                engineIDv  = makeIntCompactDescrByID('vehicleEngine', vType.engines[-1].id[0], vType.engines[-1].id[1])
                radioIDv   = makeIntCompactDescrByID('vehicleRadio',  vType.radios[-1].id[0],  vType.radios[-1].id[1])
                chassisIDv = makeIntCompactDescrByID('vehicleChassis',vType.chassis[-1].id[0], vType.chassis[-1].id[1])

                vDesc.installComponent(chassisIDv)
                vDesc.installComponent(engineIDv)
                vDesc.installTurret(turretIDv, gunIDv)
                vDesc.installComponent(radioIDv)

                compDescr[vehicleIdx] = vDesc.makeCompactDescr()

                if tankmenMapping and vehicleIdx in tankmenMapping:
                    vehicleTankmen[vehicleIdx] = tankmenMapping[vehicleIdx]
                else:
                    crewList = []
                    for _ in range(len(vType.crewRoles)):
                        crewList.append(tankmenID)
                        tankmenID += 1
                    vehicleTankmen[vehicleIdx] = crewList

                vehicleIdx += 1
                vehicle_count += 1

            except Exception as e:
                LOG_DEBUG('Error creating vehicle: %s' % str(e))
                continue

        LOG_DEBUG('Created %d vehicles' % vehicle_count)

        data[GUI_ITEM_TYPE.VEHICLE] = {
            'repair':                  {},
            'lastCrew':                vehicleTankmen,
            'settings':                {},
            'compDescr':               compDescr,
            'eqs':                     {},
            'shells':                  {},
            'customizationExpiryTime': {},
            'lock':                    {},
            'shellsLayout':            {},
            'vehicle':                 {}
        }

        data['customizations'] = {
            False: {},
            True:  compDescr
        }

        LOG_DEBUG('Offline inventory created successfully')
        return {'inventory': data}

    except Exception as e:
        LOG_DEBUG('getOfflineInventory error: %s' % str(e))
        import traceback
        LOG_DEBUG(traceback.format_exc())
        return {'inventory': {i: {} for i in GUI_ITEM_TYPE.ALL()}}


def getOfflineStats():
    """Получение оффлайн статистики с полным экипажем"""
    try:
        LOG_DEBUG('Creating stats')
        unlocksSet  = set()
        vehiclesSet = set()
        tankmenDict = {}

        for nationID in nations.INDICES.values():
            try:
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleChassis',  nationID, i) for i in g_cache.chassis(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleEngine',   nationID, i) for i in g_cache.engines(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleFuelTank', nationID, i) for i in g_cache.fuelTanks(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleRadio',    nationID, i) for i in g_cache.radios(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleTurret',   nationID, i) for i in g_cache.turrets(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleGun',      nationID, i) for i in g_cache.guns(nationID).keys()}
                unlocksSet |= {vehicles.makeIntCompactDescrByID('shell',           nationID, i) for i in g_cache.shells(nationID).keys()}

                vData = {vehicles.makeIntCompactDescrByID('vehicle', nationID, i) for i in g_list.getList(nationID).keys()}
                unlocksSet  |= vData
                vehiclesSet |= vData
            except Exception as e:
                LOG_DEBUG('Error loading nation %s: %s' % (nationID, str(e)))
                continue

        # attrs
        attrs = 0
        for field in dir(ACCOUNT_ATTR):
            value = getattr(ACCOUNT_ATTR, field, None)
            if isinstance(value, (int, long)):
                attrs |= value

        vehTypeXP = {i: 0 for i in vehiclesSet}

        # Создаём экипаж
        tankmenID = 1
        for vehicleCompDescr in vehiclesSet:
            try:
                vehicle     = vehicles.VehicleDescr(compactDescr=vehicleCompDescr)
                vType       = vehicle.type
                nationID    = vType.id[0]
                vehicleTypeID = vType.id[1]

                try:
                    nConfig = tankmen.getNationConfig(nationID)
                    if not nConfig:
                        continue
                except:
                    continue

                for slotIdx, crewRole in enumerate(vType.crewRoles):
                    if isinstance(crewRole, (list, tuple)):
                        role = crewRole[0]
                    else:
                        role = crewRole

                    try:
                        cd = _makeTankmanCompDescr(nationID, vehicleTypeID, role, roleLevel=100)
                        if cd is None:
                            continue

                        tankmenDict[tankmenID] = {
                            'compDescr':          cd,
                            'vehicleNativeDescr': vehicleCompDescr,
                            'vehicleDescr':       vehicleCompDescr,
                        }
                        tankmenID += 1

                    except Exception as e:
                        LOG_DEBUG('Tankman slot %d error nation=%d veh=%d: %s' % (
                            slotIdx, nationID, vehicleTypeID, str(e)))
                        continue

            except Exception as e:
                LOG_DEBUG('Error creating crew for vehicle: %s' % str(e))
                continue

        LOG_DEBUG('Created %d tankmen' % len(tankmenDict))

        return {
            'stats': {
                'crystalExchangeRate':        200,
                'berths':                     40000,
                'accOnline':                  0,
                'autoBanTime':                0,
                'gold':                       10000000,
                'crystal':                    10000000,
                'isFinPswdVerified':          True,
                'finPswdAttemptsLeft':         0,
                'denunciationsLeft':           0,
                'freeVehiclesLeft':            0,
                'refSystem':                  {'referrals': {}},
                'slots':                      1000,
                'battlesTillCaptcha':          0,
                'hasFinPassword':              True,
                'clanInfo':                   (None, None, 0, 0, 0),
                'unlocks':                    unlocksSet,
                'mayConsumeWalletResources':   True,
                'freeTMenLeft':                0,
                'vehicleSellsLeft':            0,
                'SPA':                        {'/common/goldfish_bonus_applied/': u'1'},
                'vehTypeXP':                  vehTypeXP,
                'unitAcceptDeadline':          0,
                'globalVehicleLocks':          {},
                'freeXP':                     10000000,
                'captchaTriesLeft':            0,
                'fortResource':                0,
                'premiumExpiryTime':           8000,
                'tkillIsSuspected':            False,
                'credits':                    100000000,
                'vehTypeLocks':                {},
                'dailyPlayHours':              [0],
                'globalRating':                9000,
                'restrictions':                {},
                'oldVehInvID':                 0,
                'accOffline':                  0,
                'dossier':                     '',
                'multipliedXPVehs':            {},
                'tutorialsCompleted':          33553532,
                'eliteVehicles':              vehiclesSet,
                'playLimits':                 ((0, ''), (0, '')),
                'clanDBID':                    0,
                'attrs':                       attrs,
                'tankmen':                     tankmenDict,
            }
        }

    except Exception as e:
        LOG_DEBUG('getOfflineStats error: %s' % str(e))
        import traceback
        LOG_DEBUG(traceback.format_exc())
        return {'stats': {}}


def getOfflineShop():
    """Получение оффлайн магазина"""
    try:
        LOG_DEBUG('Creating offline shop')
        shopItems = {}
        items.init(True, shopItems)
        return {
            'crystalExchangeRate':                 200,
            'camouflageCost': {
                0:  (250,    True),
                30: (100000, False),
                7:  (25000,  False)
            },
            'goodies': {
                'prices':    {},
                'notInShop': set([]),
                'goodies':   {}
            },
            'berthsPrices':                        (16, 16, [300]),
            'femalePassportChangeCost':             50,
            'freeXPConversion':                    (100000, 0.1),
            'dropSkillsCost': {
                0: {'xpReuseFraction': 0.5,  'gold': 0,  'credits': 0},
                1: {'xpReuseFraction': 0.75, 'gold': 0,  'credits': 20000},
                2: {'xpReuseFraction': 1.0,  'gold': 10, 'credits': 1000}
            },
            'refSystem': {
                'maxNumberOfReferrals': 50,
                'posByXPinTeam':        10,
                'maxReferralXPPool':    350000,
                'periods':              [(24, 3.0), (168, 2.0), (876000, 1.5)]
            },
            'playerEmblemCost': {
                0:  (15,   True),
                30: (6000, False),
                7:  (1500, False)
            },
            'premiumCost': {
                1: 1, 3: 1, 7: 1, 360: 1, 180: 1, 30: 1
            },
            'winXPFactorMode':                     0,
            'sellPriceModif':                      0.75,
            'passportChangeCost':                  50,
            'exchangeRateForShellsAndEqs':         400,
            'exchangeRate':                        400,
            'tankmanCost': (
                {
                    'isPremium':           False,
                    'baseRoleLoss':        0.20000000298023224,
                    'gold':                0,
                    'credits':             0,
                    'classChangeRoleLoss': 0.20000000298023224,
                    'roleLevel':           50
                },
                {
                    'isPremium':           False,
                    'baseRoleLoss':        0.10000000149011612,
                    'gold':                0,
                    'credits':             20000,
                    'classChangeRoleLoss': 0.10000000149011612,
                    'roleLevel':           75
                },
                {
                    'isPremium':           True,
                    'baseRoleLoss':        0.0,
                    'gold':                200,
                    'credits':             0,
                    'classChangeRoleLoss': 0.0,
                    'roleLevel':           100
                }
            ),
            'paidRemovalCost':                     0,
            'dailyXPFactor':                       100,
            'changeRoleCost':                      500,
            'isEnabledBuyingGoldShellsForCredits':  False,
            'items':                               shopItems,
            'slotsPrices':                         (9, [1]),
            'freeXPToTManXPRate':                  10,
            'defaults': {
                'items':              shopItems,
                'freeXPToTManXPRate':  0,
                'goodies':            {'prices': {}}
            },
            'sellPriceFactor':                     0.5,
            'isEnabledBuyingGoldEqsForCredits':     False,
            'playerInscriptionCost': {
                0:        (15,   True),
                7:        (1500, False),
                30:       (6000, False),
                'nations': {}
            }
        }
    except Exception as e:
        LOG_DEBUG('getOfflineShop error: %s' % str(e))
        return {}


def getOfflineQuestsProgress():
    """Получение оффлайн прогресса квестов"""
    return {
        'tokens': {},
        'potapovQuests': {
            'compDescr': '',
            'regular': {
                'tiles':     set([]),
                'rewards':   {},
                'compDescr': '',
                'selected':  set([1, 17, 31, 46, 61]),
                'lastIDs':   {},
                'slots':     2
            },
            'fallout': {
                'tiles':     set([]),
                'rewards':   {},
                'compDescr': '',
                'selected':  set([301, 401]),
                'lastIDs':   {},
                'slots':     2
            },
        },
        'quests': {}
    }