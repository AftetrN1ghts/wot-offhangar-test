import cPickle
import ResMgr

from chat_shared import CHAT_RESPONSES

IS_REQUEST_CATCHING = False

OFFLINE_SERVER_ADDRES = 'wargaming.net'
OFFLINE_NICKNAME = 'Player1'
OFFLINE_LOGIN = OFFLINE_NICKNAME + '@' + OFFLINE_SERVER_ADDRES
OFFLINE_PWD = '123456'
OFFLINE_DBID = 1

OFFLINE_GUI_CTX = cPickle.dumps({
    'databaseID': OFFLINE_DBID,
    'logUXEvents': True,
    'aogasStartedAt': 0,
    'sessionStartedAt': 0,
    'isAogasEnabled': False,
    'collectUiStats': False,
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
        'starting_time_of_a_new_day':      0
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

REQUEST_CALLBACK_TIME = 0.5