# scripts/client/gui/mods/offhangar/account_state.py

"""
Центральное хранилище состояния оффлайн-аккаунта в памяти.
Все изменения (покупки, продажи) проходят через этот модуль.
При каждом изменении автоматически сохраняется на диск.
"""

import nations
import items
from items import vehicles, tankmen, makeIntCompactDescrByID
from items.vehicles import g_list, g_cache

from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.storage import saveAccount, loadAccount, hasSave

# ==================== Глобальное состояние ====================

_state = {
    # Валюта
    'credits':    100000000,
    'gold':       10000000,
    'crystal':    10000000,
    'freeXP':     10000000,

    # Слоты и казармы
    'slots':      1000,
    'berths':     40000,

    # Техника: {invID: compactDescr (str)}
    'vehicles':   {},

    # Экипаж в технике: {invID: [tankmanID, ...]}
    'vehicleCrew': {},

    # Танкисты: {tankmanID: {'compDescr': str, 'vehicleNativeDescr': int, 'vehicleDescr': int}}
    'tankmen':    {},

    # Разблокировки: set of intCD
    'unlocks':    set(),

    # Опыт на типах техники: {intCD: xp}
    'vehTypeXP':  {},

    # Элитная техника: set of intCD
    'eliteVehicles': set(),

    # Купленные модули/снаряды: {intCD: count}
    'inventory_modules': {},

    # Следующие свободные ID
    '_nextVehicleID': 1,
    '_nextTankmanID': 1,

    # Флаг инициализации
    '_initialized': False,
}


def getState():
    """Возвращает текущее состояние"""
    return _state


def isInitialized():
    return _state['_initialized']


def initialize(force=False):
    """
    Инициализирует состояние.
    Если есть сохранение — загружает.
    Если нет — создаёт с нуля (все танки, все модули).
    """
    global _state

    if _state['_initialized'] and not force:
        return

    LOG_DEBUG('Initializing account state...')

    saved = loadAccount()
    if saved is not None:
        LOG_DEBUG('Restoring from save...')
        _state.update(saved)
        _state['_initialized'] = True
        # Восстанавливаем set-ы
        if not isinstance(_state.get('unlocks'), set):
            _state['unlocks'] = set(_state.get('unlocks', []))
        if not isinstance(_state.get('eliteVehicles'), set):
            _state['eliteVehicles'] = set(_state.get('eliteVehicles', []))
        LOG_DEBUG('State restored: %d vehicles, %d tankmen, credits=%d, gold=%d' % (
            len(_state['vehicles']), len(_state['tankmen']),
            _state['credits'], _state['gold']))
        return

    LOG_DEBUG('Creating fresh account state...')
    _createFreshState()
    _state['_initialized'] = True
    save()
    LOG_DEBUG('Fresh state created: %d vehicles, %d tankmen' % (
        len(_state['vehicles']), len(_state['tankmen'])))


def save():
    """Сохраняет текущее состояние на диск"""
    saveAccount(_state)


def _createFreshState():
    """Создаёт начальное состояние с техникой"""
    global _state

    _state['credits'] = 100000000
    _state['gold'] = 10000000
    _state['crystal'] = 10000000
    _state['freeXP'] = 10000000
    _state['slots'] = 1000
    _state['berths'] = 40000

    _state['vehicles'] = {}
    _state['vehicleCrew'] = {}
    _state['tankmen'] = {}
    _state['unlocks'] = set()
    _state['vehTypeXP'] = {}
    _state['eliteVehicles'] = set()
    _state['inventory_modules'] = {}

    vehicleIdx = 1
    tankmanIdx = 1

    # Разблокируем все компоненты
    for nationID in nations.INDICES.values():
        try:
            _state['unlocks'] |= {makeIntCompactDescrByID('vehicleChassis', nationID, i)
                                   for i in g_cache.chassis(nationID).keys()}
            _state['unlocks'] |= {makeIntCompactDescrByID('vehicleEngine', nationID, i)
                                   for i in g_cache.engines(nationID).keys()}
            _state['unlocks'] |= {makeIntCompactDescrByID('vehicleRadio', nationID, i)
                                   for i in g_cache.radios(nationID).keys()}
            _state['unlocks'] |= {makeIntCompactDescrByID('vehicleTurret', nationID, i)
                                   for i in g_cache.turrets(nationID).keys()}
            _state['unlocks'] |= {makeIntCompactDescrByID('vehicleGun', nationID, i)
                                   for i in g_cache.guns(nationID).keys()}
            try:
                _state['unlocks'] |= {makeIntCompactDescrByID('vehicleFuelTank', nationID, i)
                                       for i in g_cache.fuelTanks(nationID).keys()}
            except:
                pass
            try:
                _state['unlocks'] |= {makeIntCompactDescrByID('shell', nationID, i)
                                       for i in g_cache.shells(nationID).keys()}
            except:
                pass

            vData = {makeIntCompactDescrByID('vehicle', nationID, i)
                     for i in g_list.getList(nationID).keys()}
            _state['unlocks'] |= vData
            _state['eliteVehicles'] |= vData

            for vIntCD in vData:
                _state['vehTypeXP'][vIntCD] = 0
        except Exception as e:
            LOG_DEBUG('Fresh state nation %d error: %s' % (nationID, str(e)))
            continue

    # Добавляем первые 100 танков в инвентарь
    addedCount = 0
    for value in list(g_list._VehicleList__ids.values()):
        if addedCount >= 100:
            break
        try:
            result = addVehicleToInventory(value, withCrew=True, skipSave=True)
            if result is not None:
                addedCount += 1
        except Exception as e:
            continue

    LOG_DEBUG('Fresh state: added %d vehicles' % addedCount)


# ==================== Операции с валютой ====================

def getCredits():
    return _state['credits']


def getGold():
    return _state['gold']


def getCrystal():
    return _state['crystal']


def getFreeXP():
    return _state['freeXP']


def spendCredits(amount):
    """Списывает кредиты. Возвращает True если хватило."""
    if _state['credits'] >= amount:
        _state['credits'] -= amount
        save()
        return True
    return False


def spendGold(amount):
    """Списывает золото. Возвращает True если хватило."""
    if _state['gold'] >= amount:
        _state['gold'] -= amount
        save()
        return True
    return False


def spendCrystal(amount):
    if _state['crystal'] >= amount:
        _state['crystal'] -= amount
        save()
        return True
    return False


def addCredits(amount):
    _state['credits'] += amount
    save()


def addGold(amount):
    _state['gold'] += amount
    save()


def addCrystal(amount):
    _state['crystal'] += amount
    save()


def addFreeXP(amount):
    _state['freeXP'] += amount
    save()


def spendFreeXP(amount):
    if _state['freeXP'] >= amount:
        _state['freeXP'] -= amount
        save()
        return True
    return False


# ==================== Операции с техникой ====================

def addVehicleToInventory(typeID, withCrew=True, skipSave=False):
    """
    Добавляет танк в инвентарь.
    typeID — tuple (nationID, vehicleTypeID) или compact descriptor int.
    Возвращает invID или None при ошибке.
    """
    try:
        if isinstance(typeID, (int, long)):
            # compact descriptor
            vehicle = vehicles.VehicleDescr(compactDescr=typeID)
        else:
            vehicle = vehicles.VehicleDescr(typeID=typeID)

        vType = vehicle.type

        # Устанавливаем топовые модули
        if len(vType.turrets) == 0 or len(vType.turrets[-1]) <= 1:
            return None

        turret = vType.turrets[-1][-1]
        if not turret.guns:
            return None

        gun = turret.guns[-1]
        gunID = makeIntCompactDescrByID('vehicleGun', gun.id[0], gun.id[1])
        turretID = makeIntCompactDescrByID('vehicleTurret', turret.id[0], turret.id[1])
        engineID = makeIntCompactDescrByID('vehicleEngine', vType.engines[-1].id[0], vType.engines[-1].id[1])
        radioID = makeIntCompactDescrByID('vehicleRadio', vType.radios[-1].id[0], vType.radios[-1].id[1])
        chassisID = makeIntCompactDescrByID('vehicleChassis', vType.chassis[-1].id[0], vType.chassis[-1].id[1])

        vehicle.installComponent(chassisID)
        vehicle.installComponent(engineID)
        vehicle.installTurret(turretID, gunID)
        vehicle.installComponent(radioID)

        invID = _state['_nextVehicleID']
        _state['_nextVehicleID'] += 1

        _state['vehicles'][invID] = vehicle.makeCompactDescr()

        # Создаём экипаж
        if withCrew:
            crewList = []
            for slotIdx, crewRole in enumerate(vType.crewRoles):
                role = crewRole[0] if isinstance(crewRole, (list, tuple)) else crewRole
                tankmanID = _createTankman(
                    vType.id[0], vType.id[1], role,
                    vehicles.makeIntCompactDescrByID('vehicle', vType.id[0], vType.id[1])
                )
                if tankmanID is not None:
                    crewList.append(tankmanID)
                else:
                    crewList.append(None)
            _state['vehicleCrew'][invID] = crewList

        if not skipSave:
            save()

        return invID

    except Exception as e:
        LOG_DEBUG('addVehicleToInventory error: %s' % str(e))
        return None


def removeVehicleFromInventory(invID):
    """Удаляет танк из инвентаря. Возвращает True при успехе."""
    if invID not in _state['vehicles']:
        return False

    # Удаляем экипаж
    crewList = _state['vehicleCrew'].pop(invID, [])
    for tankmanID in crewList:
        if tankmanID is not None and tankmanID in _state['tankmen']:
            del _state['tankmen'][tankmanID]

    del _state['vehicles'][invID]
    save()
    return True


def getVehicleByInvID(invID):
    """Возвращает compactDescr танка по invID"""
    return _state['vehicles'].get(invID)


def getVehicleInvIDs():
    """Возвращает список invID всех танков"""
    return list(_state['vehicles'].keys())


def hasVehicleByIntCD(intCD):
    """Проверяет, есть ли танк с данным intCD в инвентаре"""
    for invID, compDescr in _state['vehicles'].iteritems():
        try:
            vDesc = vehicles.VehicleDescr(compactDescr=compDescr)
            vIntCD = makeIntCompactDescrByID('vehicle', vDesc.type.id[0], vDesc.type.id[1])
            if vIntCD == intCD:
                return True
        except:
            continue
    return False


def findVehicleInvID(intCD):
    """Находит invID танка по intCD. Возвращает None если не найден."""
    for invID, compDescr in _state['vehicles'].iteritems():
        try:
            vDesc = vehicles.VehicleDescr(compactDescr=compDescr)
            vIntCD = makeIntCompactDescrByID('vehicle', vDesc.type.id[0], vDesc.type.id[1])
            if vIntCD == intCD:
                return invID
        except:
            continue
    return None


# ==================== Операции с экипажем ====================

def _createTankman(nationID, vehicleTypeID, role, vehicleCompDescr):
    """Создаёт танкиста и добавляет в хранилище. Возвращает tankmanID."""
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
            roleLevel=100,
            skills=[],
            isFemale=False
        )
        cd = tDescr.makeCompactDescr()
        if cd is None:
            return None

        tankmanID = _state['_nextTankmanID']
        _state['_nextTankmanID'] += 1

        _state['tankmen'][tankmanID] = {
            'compDescr': cd,
            'vehicleNativeDescr': vehicleCompDescr,
            'vehicleDescr': vehicleCompDescr,
        }
        return tankmanID

    except Exception as e:
        LOG_DEBUG('_createTankman error n=%d v=%d r=%s: %s' % (
            nationID, vehicleTypeID, role, str(e)))
        return None


def recruitTankman(nationID, vehicleTypeID, role, vehicleCompDescr):
    """Рекрутирует нового танкиста. Возвращает tankmanID."""
    tankmanID = _createTankman(nationID, vehicleTypeID, role, vehicleCompDescr)
    if tankmanID is not None:
        save()
    return tankmanID


def dismissTankman(tankmanID):
    """Увольняет танкиста."""
    if tankmanID in _state['tankmen']:
        del _state['tankmen'][tankmanID]
        # Убираем из экипажей
        for invID, crew in _state['vehicleCrew'].iteritems():
            for i, tid in enumerate(crew):
                if tid == tankmanID:
                    crew[i] = None
        save()
        return True
    return False


# ==================== Операции со слотами ====================

def buySlot():
    """Покупка слота в ангаре"""
    _state['slots'] += 1
    save()
    return True


def buyBerths(count=16):
    """Покупка мест в казарме"""
    _state['berths'] += count
    save()
    return True


# ==================== Операции с модулями ====================

def addModuleToInventory(intCD, count=1):
    """Добавляет модуль/снаряд в инвентарь"""
    current = _state['inventory_modules'].get(intCD, 0)
    _state['inventory_modules'][intCD] = current + count
    save()


def removeModuleFromInventory(intCD, count=1):
    """Удаляет модуль из инвентаря"""
    current = _state['inventory_modules'].get(intCD, 0)
    if current >= count:
        _state['inventory_modules'][intCD] = current - count
        if _state['inventory_modules'][intCD] <= 0:
            del _state['inventory_modules'][intCD]
        save()
        return True
    return False


def getModuleCount(intCD):
    """Количество модулей в инвентаре"""
    return _state['inventory_modules'].get(intCD, 0)


# ==================== Установка модулей ====================

def installModule(invID, moduleIntCD):
    """Устанавливает модуль на танк"""
    if invID not in _state['vehicles']:
        return False

    try:
        compDescr = _state['vehicles'][invID]
        vDesc = vehicles.VehicleDescr(compactDescr=compDescr)

        from items import getTypeOfCompactDescr
        itemTypeID = getTypeOfCompactDescr(moduleIntCD)

        if itemTypeID == items.ITEM_TYPES.vehicleTurret:
            # Для башни нужно также указать пушку
            vDesc.installTurret(moduleIntCD, 0)
        else:
            vDesc.installComponent(moduleIntCD)

        _state['vehicles'][invID] = vDesc.makeCompactDescr()
        save()
        return True

    except Exception as e:
        LOG_DEBUG('installModule error invID=%d intCD=%d: %s' % (invID, moduleIntCD, str(e)))
        return False


# ==================== Утилиты ====================

def resetAccount():
    """Полный сброс аккаунта"""
    global _state
    _state['_initialized'] = False
    from gui.mods.offhangar.storage import deleteSave
    deleteSave()
    initialize(force=True)