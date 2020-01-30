#include <sourcemod>

#include <SteamWorks>

#undef REQUIRE_PLUGIN
#include <discord>


//#define DEBUG



#define PREFIX              "[DISCORD] "

#define PERSISTENT_FILE     "zmrdiscordnotify_persistent.cfg"
#define CONFIG_FILE         "configs/zmrdiscordnotify.cfg"


ConVar g_ConVar_Hostname;


ConVar g_ConVar_PlayerNotificationInterval;
ConVar g_ConVar_PersistentFile;


//float g_flLastFirstConnect;

int g_time_LastPlayerCountUpdate;
int g_time_LastPlayerNotification;
int g_time_LastCrashReport;


char g_szToken[512];
char g_szUrl[256];


public void OnPluginStart()
{
    // CONVARS
    g_ConVar_Hostname = FindConVar( "hostname" );
    if ( g_ConVar_Hostname == null )
    {
        SetFailState( "Couldn't find hostname cvar!" );
    }
    

    g_ConVar_PlayerNotificationInterval = CreateConVar( "discord_playernotify", "3600", "How often (in seconds) do we allow players to notify others on Discord.", 0, true, 900.0, true, 133700.0 );
    g_ConVar_PersistentFile = CreateConVar( "discord_persistentfile", PERSISTENT_FILE, "Name of the file to use. Useful if you're running multiple servers from one instance." );
    
    
    // CMDS
    RegConsoleCmd( "sm_discord", Cmd_Discord );
    
    
    
    //if ( LoadPersistentData() )
    //{
    //    SavePersistentData( true );
    //}
    
    LoadOptions();
    
    
#if defined DEBUG
    char socket[64];
    GetServerSocket( socket, sizeof( socket ) );
    
    PrintToServer( PREFIX..."Detected socket: %s", socket );
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
    
    // Let console notify without limits.
    if ( client > 0 && timeDelta < g_ConVar_PlayerNotificationInterval.IntValue )
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
    GetServerSocket( szConnect, sizeof( szConnect ) );
    
    
    char szMsg[1024];
    
    BuildJson( szMsg, sizeof( szMsg ),
        g_szToken,
        szServerName,
        szConnect,
        GetClientCount( false ),
        MaxClients,
        szPlayerName );
        
#if defined DEBUG
    PrintToServer( PREFIX..."Json:" );
    PrintToServer( "%s", szMsg );
#endif
    
    
    Handle hRequest = SteamWorks_CreateHTTPRequest( k_EHTTPMethodPOST, g_szUrl );
    SteamWorks_SetHTTPRequestRawPostBody( hRequest, "application/json", szMsg, strlen( szMsg ) );
    
    
    if ( !hRequest || !SteamWorks_SetHTTPCallbacks( hRequest, OnRequestCompleted ) || !SteamWorks_SendHTTPRequest( hRequest ) )
    {
        delete hRequest;
    }
    
    
    
    g_time_LastPlayerNotification = iCurTime;
    
    return true;
}

public void OnRequestCompleted( Handle hRequest, bool bFailure, bool bRequestSuccessful, EHTTPStatusCode eStatusCode )
{
	if ( !bFailure && bRequestSuccessful && eStatusCode == k_EHTTPStatusCode200OK )
	{
		SteamWorks_GetHTTPResponseBodyCallback( hRequest, OnBodyCallback );
	}

	delete hRequest;
}

public void OnBodyCallback( const char[] szData )
{
#if defined DEBUG
    PrintToServer( PREFIX..."Return body:" );
    PrintToServer( "%s", szData );
#endif
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

stock void GetServerSocket( char[] sz, int len )
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

stock void BuildJson(
    char[] sz,
    int len,
    const char[] szToken,
    const char[] szServerName,
    const char[] szConnect,
    int nPlayers,
    int nMaxPlayers,
    const char[] szPlayerName )
{
    // \"username\":\"%s\" 
    FormatEx( sz, len,
        "{"...
        "\"token\":\"%s\","...
        "\"hostname\":\"%s\","...
        "\"join_ip\":\"%s\","...
        "\"num_players\":%i,"...
        "\"max_players\":%i,"...
        "\"player_name\":\"%s\""...
        "}",
        szToken,
        szServerName,
        szConnect,
        nPlayers,
        nMaxPlayers,
        szPlayerName );
}

stock bool LoadOptions()
{
    KeyValues kv = new KeyValues( "DiscordNotify" );
    
    
    char szFile[PLATFORM_MAX_PATH];
    BuildPath( Path_SM, szFile, sizeof( szFile ), CONFIG_FILE );
    
    if ( !kv.ImportFromFile( szFile ) )
    {
        delete kv;
        return false;
    }
    
    
    
    kv.GetString( "token", g_szToken, sizeof( g_szToken ) );
    kv.GetString( "url", g_szUrl, sizeof( g_szUrl ) );
    
#if defined DEBUG
    PrintToServer( PREFIX..."Token: %s", g_szToken );
    PrintToServer( PREFIX..."Url: %s", g_szUrl );
#endif
    
    
    delete kv;
    
    return true;
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
    
    
    //char szMsg[1024];
    //FormatEx( szMsg, sizeof( szMsg ), "```%s\\n%s\\nOops! %s crashed :(```", SYNTAX_COLOR_RED, szServerName, szFixedMap );
    
    //BuildJson( szServerName, szMsg, sizeof( szMsg ) );
    
    
    //Discord_SendMessage( DISCORD_KEY, szMsg );
    
    
    g_time_LastPlayerNotification = iCurTime;
    
    return true;
}

