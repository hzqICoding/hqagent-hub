; Keep the program tree separate from %LOCALAPPDATA%\HQAgent-Hub user data.
; This product uses a fixed per-user installation directory (OTA architecture section 14).
!macro NSIS_HOOK_PREINSTALL
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\HQAgent-Hub"
  SetOutPath "$INSTDIR"
!macroend

; Only remove the shell's autostart registration. Never touch the user data root.
!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "HQAgent-Hub"
!macroend
