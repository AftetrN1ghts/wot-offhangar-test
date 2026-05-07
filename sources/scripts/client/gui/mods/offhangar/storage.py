# scripts/client/gui/mods/offhangar/storage.py

"""
Персистентное хранилище аккаунта.
Сохраняет/загружает состояние в JSON файл.
"""

import os
import json
import time
import shutil
import ResMgr

from gui.mods.offhangar.logging import LOG_DEBUG

# Путь к файлу сохранения
_SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'offhangar_saves')
_SAVE_FILE = 'account_save.json'
_BACKUP_FILE = 'account_save.backup.json'


def _getSavePath():
    """Возвращает полный путь к файлу сохранения"""
    saveDir = os.path.normpath(_SAVE_DIR)
    if not os.path.exists(saveDir):
        try:
            os.makedirs(saveDir)
        except OSError:
            # Фоллбек на папку рядом с клиентом
            saveDir = os.path.normpath(os.path.join('.', 'offhangar_saves'))
            if not os.path.exists(saveDir):
                os.makedirs(saveDir)
    return os.path.join(saveDir, _SAVE_FILE)


def _getBackupPath():
    saveDir = os.path.dirname(_getSavePath())
    return os.path.join(saveDir, _BACKUP_FILE)


def saveAccount(stateDict):
    """
    Сохраняет состояние аккаунта в JSON файл.
    stateDict — словарь с полями: credits, gold, crystal, freeXP,
                                   vehicles, tankmen, unlocks и т.д.
    """
    try:
        savePath = _getSavePath()
        backupPath = _getBackupPath()

        # Бэкап предыдущего сейва
        if os.path.exists(savePath):
            try:
                shutil.copy2(savePath, backupPath)
            except Exception as e:
                LOG_DEBUG('Backup failed: %s' % str(e))

        # Конвертируем set в list для JSON
        serializable = _makeSerializable(stateDict)
        serializable['_saveTime'] = time.time()
        serializable['_saveVersion'] = 2

        tmpPath = savePath + '.tmp'
        with open(tmpPath, 'w') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

        # Атомарная замена
        if os.path.exists(savePath):
            os.remove(savePath)
        os.rename(tmpPath, savePath)

        LOG_DEBUG('Account saved to %s' % savePath)
        return True

    except Exception as e:
        LOG_DEBUG('saveAccount error: %s' % str(e))
        import traceback
        LOG_DEBUG(traceback.format_exc())
        return False


def loadAccount():
    """
    Загружает состояние аккаунта из JSON файла.
    Возвращает dict или None если файла нет.
    """
    try:
        savePath = _getSavePath()
        if not os.path.exists(savePath):
            LOG_DEBUG('No save file found at %s' % savePath)
            return None

        with open(savePath, 'r') as f:
            data = json.load(f)

        # Конвертируем list обратно в set где нужно
        restored = _restoreTypes(data)
        LOG_DEBUG('Account loaded from %s (saved at %s)' % (
            savePath, time.ctime(data.get('_saveTime', 0))))
        return restored

    except Exception as e:
        LOG_DEBUG('loadAccount error: %s, trying backup...' % str(e))
        return _loadBackup()


def _loadBackup():
    """Попытка загрузить бэкап"""
    try:
        backupPath = _getBackupPath()
        if not os.path.exists(backupPath):
            return None

        with open(backupPath, 'r') as f:
            data = json.load(f)

        restored = _restoreTypes(data)
        LOG_DEBUG('Account loaded from backup')
        return restored

    except Exception as e:
        LOG_DEBUG('Backup load failed: %s' % str(e))
        return None


def deleteSave():
    """Удаляет файл сохранения"""
    try:
        savePath = _getSavePath()
        if os.path.exists(savePath):
            os.remove(savePath)
            LOG_DEBUG('Save deleted')
        backupPath = _getBackupPath()
        if os.path.exists(backupPath):
            os.remove(backupPath)
    except Exception as e:
        LOG_DEBUG('deleteSave error: %s' % str(e))


def hasSave():
    """Проверяет наличие файла сохранения"""
    return os.path.exists(_getSavePath())


def _makeSerializable(obj):
    """Рекурсивно конвертирует объекты для JSON"""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.iteritems():
            # JSON ключи всегда строки
            key = str(k)
            result[key] = _makeSerializable(v)
        return result
    elif isinstance(obj, set):
        return {'__type__': 'set', '__data__': sorted(list(obj))}
    elif isinstance(obj, frozenset):
        return {'__type__': 'frozenset', '__data__': sorted(list(obj))}
    elif isinstance(obj, tuple):
        return {'__type__': 'tuple', '__data__': [_makeSerializable(i) for i in obj]}
    elif isinstance(obj, list):
        return [_makeSerializable(i) for i in obj]
    elif isinstance(obj, (int, long, float, bool)):
        return obj
    elif isinstance(obj, (str, unicode)):
        return obj
    elif obj is None:
        return None
    else:
        # Для неизвестных типов пытаемся сохранить как строку
        return {'__type__': 'unknown', '__repr__': repr(obj)}


def _restoreTypes(obj):
    """Рекурсивно восстанавливает типы из JSON"""
    if isinstance(obj, dict):
        if '__type__' in obj:
            t = obj['__type__']
            if t == 'set':
                return set(obj['__data__'])
            elif t == 'frozenset':
                return frozenset(obj['__data__'])
            elif t == 'tuple':
                return tuple(_restoreTypes(i) for i in obj['__data__'])
            elif t == 'unknown':
                return None
        result = {}
        for k, v in obj.iteritems():
            if k.startswith('_save'):
                continue
            # Пытаемся восстановить числовые ключи
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