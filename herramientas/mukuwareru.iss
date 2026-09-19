; Instalador de Mukuwareru para Inno Setup 6.
;
; No se compila a mano: lo invoca herramientas/empaquetar.py, que le pasa la
; version, la carpeta compilada y la de salida con /D. Asi la version vive en un
; unico sitio (mukuwareru/__init__.py) y no hay que tocar este archivo al publicar.
;
; Instala por usuario en %LOCALAPPDATA%\Programs\Mukuwareru, la misma carpeta que
; usa instalar.py, para que ambos caminos convivan sin duplicar los datos. Al ser
; por usuario no pide permisos de administrador ni muestra el aviso de UAC.

#ifndef Version
  #define Version "0.0.0"
#endif

; Estos tres los pasa normalmente empaquetar.py con /D, pero se les da un valor
; por defecto para poder compilar el guion directamente desde Inno Setup (IDE
; o "Compilar" con el boton derecho) sin que falle con "Undeclared identifier".
#ifndef Origen
  #define Origen GetEnv("TEMP") + "\mukuwareru-dist\Mukuwareru"
#endif
#ifndef Salida
  #define Salida GetEnv("USERPROFILE") + "\Mukuwareru-Instalador"
#endif
#ifndef Icono
  #define Icono SourcePath + "..\mukuwareru\recursos\mukuwareru.ico"
#endif

#define Nombre "Mukuwareru"
#define Ejecutable "Mukuwareru.exe"

[Setup]
; El AppId identifica el producto entre versiones: cambiarlo haria que una
; version nueva se instalase al lado de la vieja en vez de reemplazarla. Este es
; nuevo a proposito, distinto del que llevaba StudyHub: son productos distintos
; para Windows, en carpetas distintas. La migracion de datos de la instalacion
; antigua la hace herramientas/instalar.py, no el instalador.
AppId={{C4E81B37-2A6D-4F19-8B52-6D0F7A93E1C8}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher=Mukuwareru
VersionInfoVersion={#Version}

DefaultDirName={localappdata}\Programs\{#Nombre}
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableWelcomePage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir={#Salida}
OutputBaseFilename={#Nombre}-Setup-{#Version}
SetupIconFile={#Icono}
UninstallDisplayIcon={app}\{#Ejecutable}
WizardStyle=modern

; El grueso son las DLL de Qt, que comprimen muy bien: 144 MB bajan a ~50 MB.
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Se vacia _internal antes de copiar: si no, los archivos de una compilacion
; anterior que ya no existen se quedarian ahi para siempre. Nunca se listan
; datos, Library ni logs, y esa omision es deliberada.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origen}\{#Ejecutable}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\_internal\*"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Se crean vacias para que la aplicacion encuentre el sitio al primer arranque.
; Al desinstalar, Inno solo borra un directorio si quedo vacio: si hay datos o
; PDFs dentro, sobreviven.
Name: "{app}\datos"
Name: "{app}\Library"

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; Tasks: escritorio

[Run]
Filename: "{app}\{#Ejecutable}"; Description: "{cm:LaunchProgram,{#Nombre}}"; \
    Flags: nowait postinstall skipifsilent

[Messages]
es.WelcomeLabel2=Se instalara [name/ver] en este equipo.%n%nSi ya lo tenias instalado, se actualizara el programa y se conservaran intactos tu progreso, tus sesiones, tus anotaciones y tus PDFs.
