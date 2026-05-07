# scripts/client/gui/mods/offhangar/shop_actions.py

"""
Механика покупок и продаж для оффлайн-ангара.
Обрабатывает реальную экономику: проверка баланса, списание валюты,
добавление/удаление из инвентаря.
"""

import items
from items import vehicles, tankmen, makeIntCompactDescrByID, getTypeOfCompactDescr
from items.vehicles import g_list, g_cache

from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar import account_state as state


# ==================== Получение цен ====================

def getVehiclePrice(intCD):
    """
    Возвращает цену танка: (credits, gold).
    """
    try:
        from gui.mods.offhangar.data import getOfflineShop
        shopData = getOfflineShop()
        shopItems = shopData.get('items', {})

        if intCD in shopItems:
            itemData = shopItems[intCD]
            if isinstance(itemData, dict):
                return (itemData.get('credits', 0), itemData.get('gold', 0))
            elif isinstance(itemData, tuple) and len(itemData) >= 2:
                return itemData[:2]

        # Фоллбек: пытаемся получить из XML
        vDesc = vehicles.VehicleDescr(compactDescr=intCD)
        vType = vDesc.type
        price = getattr(vType, 'price', (0, 0))
        if isinstance(price, (list, tuple)) and len(price) >= 2:
            return (price[0], price[1])
        return (0, 0)

    except Exception as e:
        LOG_DEBUG('getVehiclePrice error intCD=%s: %s' % (intCD, str(e)))
        return (0, 0)


def getVehicleSellPrice(intCD):
    """Возвращает цену продажи танка (50% от покупной)"""
    buyPrice = getVehiclePrice(intCD)
    factor = 0.5
    return (int(buyPrice[0] * factor), int(buyPrice[1] * factor))


def getModulePrice(intCD):
    """Возвращает цену модуля: (credits, gold)"""
    try:
        from gui.mods.offhangar.data import getOfflineShop
        shopData = getOfflineShop()
        shopItems = shopData.get('items', {})

        if intCD in shopItems:
            itemData = shopItems[intCD]
            if isinstance(itemData, dict):
                return (itemData.get('credits', 0), itemData.get('gold', 0))
            elif isinstance(itemData, tuple) and len(itemData) >= 2:
                return itemData[:2]

        return (0, 0)
    except:
        return (0, 0)


# ==================== Покупка танков ====================

class PurchaseResult(object):
    """Результат операции покупки/продажи"""
    def __init__(self, success, errorCode='', invID=None, message=''):
        self.success = success
        self.errorCode = errorCode
        self.invID = invID
        self.message = message

    def __repr__(self):
        return 'PurchaseResult(success=%s, error=%s, invID=%s, msg=%s)' % (
            self.success, self.errorCode, self.invID, self.message)


def buyVehicle(intCD, buyShells=True, recruitCrew=True, tmanCostIdx=0):
    """
    Покупка танка.
    intCD — compact descriptor типа техники.
    buyShells — покупать ли снаряды.
    recruitCrew — нанимать ли экипаж.
    tmanCostIdx — уровень экипажа (0=50%, 1=75%, 2=100%).
    
    Возвращает PurchaseResult.
    """
    try:
        LOG_DEBUG('buyVehicle intCD=%d shells=%s crew=%s tmanCost=%d' % (
            intCD, buyShells, recruitCrew, tmanCostIdx))

        # Проверяем, нет ли уже такого танка
        if state.hasVehicleByIntCD(intCD):
            return PurchaseResult(False, 'VEHICLE_ALREADY_OWNED',
                                  message='Vehicle already in inventory')

        # Получаем цену
        price = getVehiclePrice(intCD)
        creditsCost = price[0]
        goldCost = price[1]

        # Цена экипажа
        crewCreditsCost = 0
        crewGoldCost = 0
        if recruitCrew:
            tmanCosts = [
                {'credits': 0, 'gold': 0},        # 50% экипаж — бесплатно
                {'credits': 20000, 'gold': 0},     # 75%
                {'credits': 0, 'gold': 200},        # 100%
            ]
            if 0 <= tmanCostIdx < len(tmanCosts):
                cost = tmanCosts[tmanCostIdx]
                # Считаем количество членов экипажа
                try:
                    vDesc = vehicles.VehicleDescr(compactDescr=intCD)
                    crewCount = len(vDesc.type.crewRoles)
                except:
                    crewCount = 4  # фоллбек
                crewCreditsCost = cost['credits'] * crewCount
                crewGoldCost = cost['gold'] * crewCount

        totalCredits = creditsCost + crewCreditsCost
        totalGold = goldCost + crewGoldCost

        # Проверяем баланс
        if totalCredits > 0 and state.getCredits() < totalCredits:
            return PurchaseResult(False, 'NOT_ENOUGH_CREDITS',
                                  message='Need %d credits, have %d' % (
                                      totalCredits, state.getCredits()))

        if totalGold > 0 and state.getGold() < totalGold:
            return PurchaseResult(False, 'NOT_ENOUGH_GOLD',
                                  message='Need %d gold, have %d' % (
                                      totalGold, state.getGold()))

        # Списываем валюту
        if totalCredits > 0:
            state.spendCredits(totalCredits)
        if totalGold > 0:
            state.spendGold(totalGold)

        # Добавляем танк
        # Нужно получить typeID из intCD
        vDesc = vehicles.VehicleDescr(compactDescr=intCD)
        typeID = vDesc.type.id  # (nationID, vehicleTypeID)

        invID = state.addVehicleToInventory(typeID, withCrew=recruitCrew)
        if invID is None:
            # Откат валюты
            if totalCredits > 0:
                state.addCredits(totalCredits)
            if totalGold > 0:
                state.addGold(totalGold)
            return PurchaseResult(False, 'VEHICLE_ADD_FAILED',
                                  message='Failed to add vehicle to inventory')

        LOG_DEBUG('Vehicle bought: invID=%d, spent credits=%d gold=%d' % (
            invID, totalCredits, totalGold))

        return PurchaseResult(True, invID=invID,
                              message='Vehicle purchased successfully')

    except Exception as e:
        LOG_DEBUG('buyVehicle error: %s' % str(e))
        import traceback
        LOG_DEBUG(traceback.format_exc())
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


def sellVehicle(invID):
    """
    Продажа танка.
    invID — inventory ID танка.
    
    Возвращает PurchaseResult.
    """
    try:
        LOG_DEBUG('sellVehicle invID=%d' % invID)

        compDescr = state.getVehicleByInvID(invID)
        if compDescr is None:
            return PurchaseResult(False, 'VEHICLE_NOT_FOUND',
                                  message='Vehicle not in inventory')

        # Получаем intCD для расчёта цены
        vDesc = vehicles.VehicleDescr(compactDescr=compDescr)
        intCD = makeIntCompactDescrByID('vehicle', vDesc.type.id[0], vDesc.type.id[1])

        sellPrice = getVehicleSellPrice(intCD)

        # Удаляем танк
        if not state.removeVehicleFromInventory(invID):
            return PurchaseResult(False, 'REMOVE_FAILED',
                                  message='Failed to remove vehicle')

        # Начисляем валюту
        if sellPrice[0] > 0:
            state.addCredits(sellPrice[0])
        if sellPrice[1] > 0:
            state.addGold(sellPrice[1])

        LOG_DEBUG('Vehicle sold: invID=%d, received credits=%d gold=%d' % (
            invID, sellPrice[0], sellPrice[1]))

        return PurchaseResult(True, invID=invID,
                              message='Vehicle sold for %d credits, %d gold' % sellPrice)

    except Exception as e:
        LOG_DEBUG('sellVehicle error: %s' % str(e))
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


# ==================== Покупка модулей ====================

def buyModule(intCD, count=1):
    """
    Покупка модуля.
    Возвращает PurchaseResult.
    """
    try:
        price = getModulePrice(intCD)
        totalCredits = price[0] * count
        totalGold = price[1] * count

        if totalCredits > 0 and state.getCredits() < totalCredits:
            return PurchaseResult(False, 'NOT_ENOUGH_CREDITS')
        if totalGold > 0 and state.getGold() < totalGold:
            return PurchaseResult(False, 'NOT_ENOUGH_GOLD')

        if totalCredits > 0:
            state.spendCredits(totalCredits)
        if totalGold > 0:
            state.spendGold(totalGold)

        state.addModuleToInventory(intCD, count)

        LOG_DEBUG('Module bought: intCD=%d count=%d credits=%d gold=%d' % (
            intCD, count, totalCredits, totalGold))
        return PurchaseResult(True, message='Module purchased')

    except Exception as e:
        LOG_DEBUG('buyModule error: %s' % str(e))
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


def sellModule(intCD, count=1):
    """Продажа модуля"""
    try:
        price = getModulePrice(intCD)
        sellCredits = int(price[0] * 0.5) * count
        sellGold = int(price[1] * 0.5) * count

        if not state.removeModuleFromInventory(intCD, count):
            return PurchaseResult(False, 'MODULE_NOT_FOUND')

        if sellCredits > 0:
            state.addCredits(sellCredits)
        if sellGold > 0:
            state.addGold(sellGold)

        return PurchaseResult(True, message='Module sold')

    except Exception as e:
        LOG_DEBUG('sellModule error: %s' % str(e))
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


# ==================== Обмен валюты ====================

def exchangeGoldForCredits(goldAmount):
    """Обмен золота на кредиты"""
    try:
        exchangeRate = 400  # 1 золото = 400 кредитов
        if not state.spendGold(goldAmount):
            return PurchaseResult(False, 'NOT_ENOUGH_GOLD')

        creditsAmount = goldAmount * exchangeRate
        state.addCredits(creditsAmount)

        LOG_DEBUG('Exchanged %d gold for %d credits' % (goldAmount, creditsAmount))
        return PurchaseResult(True, message='Exchange successful')

    except Exception as e:
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


def exchangeFreeXP(xpAmount):
    """Конвертация свободного опыта"""
    try:
        # 25 gold = 1 free XP при стандартных настройках
        goldCost = max(1, xpAmount // 25)
        if not state.spendGold(goldCost):
            return PurchaseResult(False, 'NOT_ENOUGH_GOLD')

        state.addFreeXP(xpAmount)
        return PurchaseResult(True, message='XP converted')

    except Exception as e:
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


# ==================== Покупка слотов и казармы ====================

def buySlot():
    """Покупка слота ангара (300 золота)"""
    slotCost = 300
    if not state.spendGold(slotCost):
        return PurchaseResult(False, 'NOT_ENOUGH_GOLD')
    state.buySlot()
    return PurchaseResult(True, message='Slot purchased')


def buyBerths():
    """Покупка мест в казарме (300 золота за 16 мест)"""
    berthCost = 300
    if not state.spendGold(berthCost):
        return PurchaseResult(False, 'NOT_ENOUGH_GOLD')
    state.buyBerths(16)
    return PurchaseResult(True, message='Berths purchased')


# ==================== Рекрутирование экипажа ====================

def recruitTankman(nationID, vehicleTypeID, role, tmanCostIdx=0):
    """
    Рекрутирование танкиста.
    tmanCostIdx: 0=бесплатный(50%), 1=за кредиты(75%), 2=за золото(100%)
    """
    try:
        tmanCosts = [
            {'credits': 0, 'gold': 0, 'roleLevel': 50},
            {'credits': 20000, 'gold': 0, 'roleLevel': 75},
            {'credits': 0, 'gold': 200, 'roleLevel': 100},
        ]

        if tmanCostIdx < 0 or tmanCostIdx >= len(tmanCosts):
            tmanCostIdx = 0

        cost = tmanCosts[tmanCostIdx]

        if cost['credits'] > 0 and state.getCredits() < cost['credits']:
            return PurchaseResult(False, 'NOT_ENOUGH_CREDITS')
        if cost['gold'] > 0 and state.getGold() < cost['gold']:
            return PurchaseResult(False, 'NOT_ENOUGH_GOLD')

        if cost['credits'] > 0:
            state.spendCredits(cost['credits'])
        if cost['gold'] > 0:
            state.spendGold(cost['gold'])

        vehicleIntCD = makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
        tankmanID = state.recruitTankman(nationID, vehicleTypeID, role, vehicleIntCD)

        if tankmanID is None:
            # Откат
            if cost['credits'] > 0:
                state.addCredits(cost['credits'])
            if cost['gold'] > 0:
                state.addGold(cost['gold'])
            return PurchaseResult(False, 'RECRUIT_FAILED')

        return PurchaseResult(True, invID=tankmanID, message='Tankman recruited')

    except Exception as e:
        LOG_DEBUG('recruitTankman error: %s' % str(e))
        return PurchaseResult(False, 'INTERNAL_ERROR', message=str(e))


def dismissTankman(tankmanID):
    """Увольнение танкиста"""
    if state.dismissTankman(tankmanID):
        return PurchaseResult(True, message='Tankman dismissed')
    return PurchaseResult(False, 'TANKMAN_NOT_FOUND')