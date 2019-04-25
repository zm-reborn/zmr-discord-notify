#include <sourcemod>

#include <discord>
#include <SteamWorks>



//#define DEBUG


#define DISCORD_KEY         "zmrdiscordnotify"


#define SYNTAX_COLOR_RED    "prolog"
#define SYNTAX_COLOR_ORANGE "fix"
#define SYNTAX_COLOR_GREEN  "css"

#define PREFIX              "[DISCORD] "

#define PERSISTENT_FILE     "zmrdiscordnotify.cfg"


ConVar g_ConVar_Hostname;


ConVar g_ConVar_PlayerNotificationInterval;
ConVar g_ConVar_PlayerNotificationPrefix;
ConVar g_ConVar_PersistentFile;


//float g_flLastFirstConnect;

int g_time_LastPlayerCountUpdate;
int g_time_LastPlayerNotification;
int g_time_LastCrashReport;


int g_nMaxPlayers = 16;

public void OnPluginStart()
{
    // CONVARS
    g_ConVar_Hostname = FindConVar( "hostname" );
    if ( g_ConVar_Hostname == null )
    {
        SetFailState( "Couldn't find hostname cvar!" );
    }
    

    g_ConVar_PlayerNotificationInterval = CreateConVar( "discord_playernotify", "3600", "How often (in seconds) do we allow players to notify others on Discord.", 0, true, 900.0, true, 133700.0 );
    g_ConVar_PlayerNotificationPrefix = CreateConVar( "discord_notifyprefix", "", "Prefix of player notification. Put mentions like @here here." );
    g_ConVar_PersistentFile = CreateConVar( "discord_persistentfile", PERSISTENT_FILE, "Name of the file to use. Useful if you're running multiple servers from one instance." );
    
    
    // CMDS
    RegConsoleCmd( "sm_discord", Cmd_Discord );
    RegAdminCmd( "sm_testdiscordnewline", Cmd_TestDiscord, ADMFLAG_ROOT );
    
    
    
    //if ( LoadPersistentData() )
    //{
    //    SavePersistentData( true );
    //}
    
    
#if defined DEBUG
    char ip[64];
    GetServerIp( ip, sizeof( ip ) );
    
    PrintToServer( PREFIX..."Detected ip: %s", ip );
#endif
}

public void OnPluginEnd()
{
    //SavePersistentData();
}

public void OnMapStart()
{
}

public void OnMapEnd()
{
    //SavePersistentData();
}

public void OnClientPutInServer( int client )
{
    
}

public void OnClientPostAdminCheck( int client )
{
    //int iCurNum = ClientCount( client );
}

stock void GetColor( int playercount, char[] sz, int len )
{
    if ( playercount <= 0 )
    {
        strcopy( sz, len, "dsconfig" );
        return;
    }
    
    int maxplayers = g_nMaxPlayers;
    
    if ( playercount >= maxplayers )
    {
        // Red
        strcopy( sz, len, SYNTAX_COLOR_RED );
        return;
    }
    
    int orangeGrace = RoundFloat( maxplayers * 0.5 );
    if ( playercount >= orangeGrace )
    {
        // Orange
        strcopy( sz, len, SYNTAX_COLOR_ORANGE );
        return;
    }
    
    // Green
    strcopy( sz, len, SYNTAX_COLOR_GREEN );
}

stock int ClientCount( int ignore = 0, bool bIgnoreBots = true )
{
    int num = 0;
    
    for ( int i = 1; i <= MaxClients; ++i )
    {
        if ( i == ignore )
            continue;
        
        if ( !IsClientConnected( i ) )
            continue;
        
        if ( bIgnoreBots && IsClientInGame( i ) && IsFakeClient( i ) )
            continue;
        
        
        ++num;
    }
    
    return num;
}

stock bool LoadPersistentData()
{
    char szFile[64];
    g_ConVar_PersistentFile.GetString( szFile, sizeof( szFile ) );
    
    char szPath[PLATFORM_MAX_PATH];
    BuildPath( Path_SM, szPath, sizeof( szPath ), "data/%s", szFile );
    
    KeyValues kv = new KeyValues( "ActivityPersistent" );
    if ( !kv.ImportFromFile( szPath ) )
    {
        delete kv;
        return false;
    }
    
    
    int lastCount = kv.GetNum( "map_end_playercount", -1 );
    
    g_time_LastPlayerCountUpdate = kv.GetNum( "last_playercount_update", 0 );
    g_time_LastPlayerNotification = kv.GetNum( "last_player_notification", 0 );
    g_time_LastCrashReport = kv.GetNum( "last_crash", 0 );
    

    if ( lastCount == 0 )
    {
        char szMap[64];
        kv.GetString( "last_crash_mapname", szMap, sizeof( szMap ) );
        
        
        SendCrashNotification( szMap );
    }
    
    
    delete kv;
    
    return lastCount >= 0;
}

stock bool SavePersistentData( bool bResetCount = false )
{
    char szFile[64];
    g_ConVar_PersistentFile.GetString( szFile, sizeof( szFile ) );
    
    char szPath[PLATFORM_MAX_PATH];
    BuildPath( Path_SM, szPath, sizeof( szPath ), "data/%s", szFile );
    
    
    KeyValues kv = new KeyValues( "ActivityPersistent" );
    
    
    int saveCount;
    if ( !bResetCount )
    {
        saveCount = 1;
        
        if ( saveCount < 1 )
            saveCount = ClientCount();
    }
    else
    {
        saveCount = 0;
    }
    
    
    kv.SetNum( "map_end_playercount", saveCount );
    
    kv.SetNum( "last_playercount_update", g_time_LastPlayerCountUpdate );
    kv.SetNum( "last_player_notification", g_time_LastPlayerNotification );
    kv.SetNum( "last_crash", g_time_LastCrashReport );
    
    
    char szMap[64];
    GetCurrentMap( szMap, sizeof( szMap ) );
    kv.SetString( "last_crash_mapname", szMap );
    
    
    if ( !kv.ExportToFile( szPath ) )
    {
        LogError( PREFIX..."Couldn't save persistent data!" );
        
        delete kv;
        return false;
    }
    
    delete kv;
    
    return true;
}

public Action Cmd_Discord( int client, int args )
{
    if ( !SendNotification( client ) )
    {
        return Plugin_Handled;
    }
    
    
    char szName[64];
    GetPlayerName( client, szName, sizeof( szName ) );
    
    PrintToChatAll( PREFIX..."%s notified Discord!", szName );
    
    return Plugin_Handled;
}

stock bool SendNotification( int client )
{
    int iCurTime = GetTime();
    
    int timeDelta = iCurTime - g_time_LastPlayerNotification;
    if ( timeDelta < g_ConVar_PlayerNotificationInterval.IntValue )
    {
        ReplyToCommand( client, PREFIX..."You can't send a notification yet!" );
        return false;
    }
    
    
    char szPlayerName[64];
    GetPlayerName( client, szPlayerName, sizeof( szPlayerName ) );
    
    
    char szServerName[128];
    g_ConVar_Hostname.GetString( szServerName, sizeof( szServerName ) );
    
    Discord_EscapeString( szServerName, sizeof( szServerName ) );
    
    
    char szConnect[512];
    GetConnectLink( szConnect, sizeof( szConnect ) );
    
    
    char szPrefix[512];
    g_ConVar_PlayerNotificationPrefix.GetString( szPrefix, sizeof( szPrefix ) );
    
    if ( szPrefix[0] != 0 )
    {
        Format( szPrefix, sizeof( szPrefix ), "%s\\n", szPrefix );
    }
    
    
    char szMsg[1024];
    FormatEx( szMsg, sizeof( szMsg ), "%s```css\\n%s wants you to join %s!```%s",
        szPrefix,
        szPlayerName,
        szServerName,
        szConnect );
    
    BuildJson( szServerName, szMsg, sizeof( szMsg ) );
    
    
    Discord_SendMessage( DISCORD_KEY, szMsg );
    
    
    g_time_LastPlayerNotification = iCurTime;
    
    return true;
}

stock void GetPlayerName( int client, char[] sz, int len )
{
    if ( client )
    {
        if ( !GetClientName( client, sz, len ) )
        {
            strcopy( sz, len, "N/A" );
        }
        
        Discord_EscapeString( sz, len );
    }
    else
    {
        strcopy( sz, len, "Server Console" );
    }
}

stock void GetServerIp( char[] sz, int len )
{
    char port[32];
    GetConVarString( FindConVar( "hostport" ), port, sizeof( port ) );
    
    
    int ipaddr[4];
    SteamWorks_GetPublicIP( ipaddr );
    
    FormatEx( sz, len, "%i.%i.%i.%i:%s",
        ipaddr[0],
        ipaddr[1],
        ipaddr[2],
        ipaddr[3],
        port );
}

stock void GetConnectLink( char[] sz, int len )
{
    char ip[64];
    GetServerIp( ip, sizeof( ip ) );
    
    if ( sz[0] != 0 )
    {
        Format( sz, len, "Connect to server: steam://connect/%s", ip );
    }
}

stock void BuildJson( const char[] szUserName, char[] sz, int len )
{
    // \"username\":\"%s\" 
    Format( sz, len, "{\"content\":\"%s\"}",
        sz );
}

public Action Cmd_TestDiscord( int client, int args )
{
    Discord_SendMessage( DISCORD_KEY, "Testing\\nTesting..." );
    
    return Plugin_Handled;
}

stock bool SendCrashNotification( const char[] szMap )
{
    int iCurTime = GetTime();
    
    int timeDelta = iCurTime - g_time_LastCrashReport;
    
    // Update right now!
    g_time_LastCrashReport = iCurTime;
    
    
    if ( timeDelta < 20.0 )
    {
        return false;
    }
    
    char szFixedMap[128];
    strcopy( szFixedMap, sizeof( szFixedMap ), szMap );
    
    Discord_EscapeString( szFixedMap, sizeof( szFixedMap ) );
    
    
    char szServerName[128];
    g_ConVar_Hostname.GetString( szServerName, sizeof( szServerName ) );
    
    Discord_EscapeString( szServerName, sizeof( szServerName ) );
    
    
    char szMsg[1024];
    FormatEx( szMsg, sizeof( szMsg ), "```%s\\n%s\\nOops! %s crashed :(```", SYNTAX_COLOR_RED, szServerName, szFixedMap );
    
    BuildJson( szServerName, szMsg, sizeof( szMsg ) );
    
    
    Discord_SendMessage( DISCORD_KEY, szMsg );
    
    
    g_time_LastPlayerNotification = iCurTime;
    
    return true;
}
