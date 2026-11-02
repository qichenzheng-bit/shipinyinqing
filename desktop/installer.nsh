!include "nsDialogs.nsh"
!include "LogicLib.nsh"

Var WeiGuangAutoDeps
Var WeiGuangDepsCheckbox

!macro customWelcomePage
  !insertmacro MUI_PAGE_WELCOME
  Page custom WeiGuangDepsPage WeiGuangDepsPageLeave
!macroend

Function WeiGuangDepsPage
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 49u "微光数学可以在安装过程中自动配置 Windows 视频引擎所需的 WSL2、Docker Desktop、Node.js，以及 Codex、Gemini、CodeBuddy 官方 CLI。文件将通过官方渠道下载并验证。"
  Pop $1
  ${NSD_CreateCheckbox} 0 57u 100% 20u "自动下载并安装所有缺少的运行依赖（推荐）"
  Pop $WeiGuangDepsCheckbox
  ${NSD_Check} $WeiGuangDepsCheckbox
  ${NSD_CreateLabel} 0 85u 100% 65u "安装可能需要网络连接、管理员授权和较大磁盘空间。WSL2 首次安装后可能需要重启；Docker Desktop 的使用条款及 AI 账号登录需由你自行确认。更新不会卸载已有依赖、模型凭据或视频数据。"
  Pop $2
  nsDialogs::Show
FunctionEnd

Function WeiGuangDepsPageLeave
  ${NSD_GetState} $WeiGuangDepsCheckbox $WeiGuangAutoDeps
FunctionEnd

!macro customInstall
  ${If} $WeiGuangAutoDeps == ${BST_CHECKED}
    DetailPrint "微光数学：正在准备系统依赖，自动下载并验证来源..."
    File /oname=$PLUGINSDIR\weiguang-setup-dependencies.ps1 "${PROJECT_DIR}\setup-dependencies.ps1"
    StrCpy $R0 "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    IfFileExists "$R0" +2 0
    StrCpy $R0 "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"
    nsExec::ExecToLog '"$R0" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\weiguang-setup-dependencies.ps1" -Mode Install'
    Pop $R1
    ${If} $R1 == "3010"
      DetailPrint "WSL2 已配置，请在安装结束后重启 Windows。再次打开微光数学将自动继续。"
      MessageBox MB_OK|MB_ICONINFORMATION "Windows 系统组件已经准备，首次使用前需要重启 Windows。随后打开微光数学继续即可。"
    ${ElseIf} $R1 != "0"
      DetailPrint "依赖准备暂未完成，返回码：$R1；微光数学首次启动时可继续安装。"
      MessageBox MB_OK|MB_ICONEXCLAMATION "部分依赖未能完成安装（例如网络中断或权限不足）。软件仍已安装；打开微光数学点击「启动并进入工作台」会自动检测并继续安装。"
    ${EndIf}
  ${EndIf}
!macroend
