# WeiGuang Math Windows dependency bootstrap (run ONLY by the trusted installer/app).
# Official package-manager manifests and verified publisher signatures; no piped web scripts.
[CmdletBinding()]
param([ValidateSet('Install','Check','WSLOnly')][string]$Mode='Check')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root=Join-Path $env:LOCALAPPDATA 'WeiGuangMath'
$statePath=Join-Path $root 'setup-state.json'
$cliRoot=Join-Path $root 'cli'
$cliBin=Join-Path $cliRoot 'node_modules\.bin'
$nodeRoot=Join-Path $root 'runtimes\node'
$script:rebootRequired=$false

function Message([string]$stage,[string]$message){
    Write-Output ("[WeiGuang] "+$stage+": "+$message)
}
function Save-State([string]$stage,[string]$status,[bool]$restart){
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $json=@{
        schema_version=1; stage=$stage; status=$status;
        reboot_required=$restart; updated_at=(Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Compress
    $tmp=$statePath+'.tmp'
    [IO.File]::WriteAllText($tmp,$json,[Text.UTF8Encoding]::new($false))
    Move-Item -Path $tmp -Destination $statePath -Force
}
function Refresh-Path {
    $machine=[Environment]::GetEnvironmentVariable('Path','Machine')
    $user=[Environment]::GetEnvironmentVariable('Path','User')
    $dockerUser=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'
    $dockerMachine=Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
    $nodeDefault=Join-Path $env:ProgramFiles 'nodejs'
    if(-not (Test-Path (Join-Path $nodeRoot 'node.exe'))){
        $runtimes=Split-Path $nodeRoot -Parent
        if(Test-Path $runtimes){
            $existing=Get-ChildItem -Path $runtimes -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name.StartsWith('node-v') -and
                    (Test-Path (Join-Path $_.FullName 'node.exe')) } |
                Sort-Object Name -Descending | Select-Object -First 1
            if($existing){$script:nodeRoot=$existing.FullName}
        }
    }
    $env:Path=(@($nodeRoot,$cliBin,$dockerUser,$dockerMachine,$nodeDefault,$machine,$user) |
        Where-Object { $_ }) -join ';'
}
function Exists-Command([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}
function Is-Administrator {
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function WSL-Installed {
    $exe=Join-Path $env:windir 'System32\wsl.exe'
    if(-not (Test-Path $exe)){ return $false }
    try {
        $text=(& $exe --version 2>&1 | Out-String)
        return ($LASTEXITCODE -eq 0 -and $text -match 'WSL|Windows Subsystem|适用于 Linux 的 Windows 子系统')
    }catch { return $false }
}
function Docker-App {
    foreach($item in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
    )){if(Test-Path $item){return $item}}
    return $null
}
function Node-Ready {
    Refresh-Path
    if(-not (Exists-Command 'node.exe')){ return $false }
    try{
        $version=(& node.exe --version 2>$null | Out-String).Trim()
        $major=[int]([regex]::Match($version,'^v(\d+)').Groups[1].Value)
        return ($major -ge 20)
    }catch { return $false }
}
function Tools-Ready {
    Refresh-Path
    foreach($tool in @('codex.cmd','gemini.cmd','codebuddy.cmd')){
        $stem=[IO.Path]::GetFileNameWithoutExtension($tool)
        if(-not (Exists-Command $tool) -and -not (Exists-Command ($stem+'.exe'))) {
            return $false
        }
    }
    return $true
}
function Run-Winget([string]$package) {
    $exe=Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if(-not $exe){ return $false }
    Message 'download' ('从 Windows 软件源安装 '+$package)
    $arguments=@('install','--id',$package,'--exact','--source','winget',
       '--silent','--accept-package-agreements','--accept-source-agreements',
       '--disable-interactivity','--no-upgrade')
    try{
        $proc=Start-Process -FilePath $exe.Source -ArgumentList $arguments -Wait -PassThru -NoNewWindow
        return ($proc.ExitCode -eq 0)
    }catch{
        Message 'notice' ('Windows 软件源不可用，使用受验证的厂商下载方式：'+$package)
        return $false
    }
}
function Install-WSL {
    if(WSL-Installed){Message 'wsl' '已经安装';return}
    Message 'wsl' '需要开启 Windows WSL2，Windows 将请求管理员批准'
    if(-not (Is-Administrator)){
        $powershell=Join-Path $PSHOME 'powershell.exe'
        $args='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Mode WSLOnly'
        $proc=Start-Process -FilePath $powershell -ArgumentList $args -Wait -PassThru -Verb RunAs
        if($proc.ExitCode -ne 0){throw 'WSL2 安装未完成：没有取得必要的管理员授权'}
    }else{
        $exe=Join-Path $env:windir 'System32\wsl.exe'
        $proc=Start-Process -FilePath $exe -ArgumentList @('--install','--no-distribution') -Wait -PassThru -NoNewWindow
        if($proc.ExitCode -ne 0){throw ('WSL2 安装失败，错误代码 '+$proc.ExitCode)}
    }
    $script:rebootRequired=$true
    Message 'wsl' '系统组件已请求安装；可能需要重启 Windows 才能生效'
}
function Install-Node {
    if(Node-Ready){Message 'node' 'Node.js 20+ 已存在，跳过';return}
    Message 'node' '安装 Node.js LTS（用于三个官方 AI CLI）'
    if(Run-Winget 'OpenJS.NodeJS.LTS'){
        Refresh-Path
        if(Node-Ready){return}
    }
    # Fallback: official HTTPS distribution, verified with its SHASUMS256.txt.
    Message 'node' '从 nodejs.org 获取 Node.js LTS 并校验 SHA-256'
    $index=Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -TimeoutSec 45
    $release=$index | Where-Object { $_.lts -and $_.lts -ne $false } | Select-Object -First 1
    if(-not $release){throw 'Node.js 官方版本清单无可用 LTS 版本'}
    $version=[string]$release.version
    if($version -notmatch '^v\d+\.\d+\.\d+$'){throw 'Node.js 官方版本号不符合格式'}
    $archive='node-'+$version+'-win-x64.zip'
    $base='https://nodejs.org/dist/'+$version+'/'
    $dir=Join-Path ([IO.Path]::GetTempPath()) ('weiguang-node-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    try {
        $zip=Join-Path $dir $archive
        Invoke-WebRequest -UseBasicParsing -Uri ($base+$archive) -OutFile $zip -TimeoutSec 180
        $shas=(Invoke-WebRequest -UseBasicParsing -Uri ($base+'SHASUMS256.txt') -TimeoutSec 45).Content
        $line=($shas -split '\r?\n' | Where-Object { $_ -match ('\s'+[regex]::Escape($archive)+'\s*$') } | Select-Object -First 1)
        if(-not $line){throw 'Node.js SHA-256 校验清单没有相应文件'}
        $expected=($line.Trim() -split '\s+')[0].ToLowerInvariant()
        $actual=(Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
        if($actual -ne $expected){throw 'Node.js 官方下载文件 SHA-256 校验失败'}
        $expanded=Join-Path $dir 'unzipped'
        Expand-Archive -Path $zip -DestinationPath $expanded
        $node=Join-Path $expanded ('node-'+$version+'-win-x64')
        if(-not (Test-Path (Join-Path $node 'node.exe'))){throw 'Node.js 安装文件不完整'}
        $runtimes=Split-Path $nodeRoot -Parent
        New-Item -ItemType Directory -Path $runtimes -Force | Out-Null
        $target=Join-Path $runtimes ('node-'+$version)
        if(-not (Test-Path $target)){Move-Item -Path $node -Destination $target}
        # Preserve any existing runtime; select a verified version on later launches.
        $script:nodeRoot=$target
        Refresh-Path
        if(-not (Node-Ready)){throw 'Node.js 校验完成但运行时不可用'}
    }finally{
        Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
function Install-Docker {
    if(Docker-App){Message 'docker' 'Docker Desktop 已安装，跳过';return}
    Message 'docker' '下载安装 Docker Desktop（WSL2 / Linux 容器）'
    if(Run-Winget 'Docker.DockerDesktop'){
        if(Docker-App){return}
    }
    # The installer is executed only when the Windows publisher signature validates.
    $url='https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
    $dest=Join-Path ([IO.Path]::GetTempPath()) ('weiguang-docker-'+[guid]::NewGuid().ToString('N')+'.exe')
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest -TimeoutSec 600
        $signature=Get-AuthenticodeSignature -FilePath $dest
        if($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
           $signature.SignerCertificate.Subject -notmatch 'Docker'){
            throw 'Docker Desktop 下载文件发布者签名无效；已拒绝执行'
        }
        $proc=Start-Process -FilePath $dest -ArgumentList @('install','--user','--quiet','--backend=wsl-2') -Wait -PassThru
        if($proc.ExitCode -ne 0){throw ('Docker Desktop 安装失败，代码 '+$proc.ExitCode)}
        if(-not (Docker-App)){throw 'Docker Desktop 安装完成，但没有检测到应用程序'}
    }finally{
        Remove-Item $dest -Force -ErrorAction SilentlyContinue
    }
}
function Install-ModelCLIs {
    if(Tools-Ready){Message 'ai-cli' 'Codex、Gemini、CodeBuddy 均已安装';return}
    Message 'ai-cli' '通过 npm 官方仓库安装三个 CLI，仅存放于当前用户目录'
    Refresh-Path
    $npm=Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
    if(-not $npm){throw 'Node.js npm 未就绪，无法安装三个 AI CLI'}
    New-Item -ItemType Directory -Path $cliRoot -Force | Out-Null
    # One transaction: subsequent --no-save npm calls would prune other CLIs.
    $arguments=@('install','--prefix',$cliRoot,'--no-save','--no-audit','--no-fund',
      '--registry=https://registry.npmjs.org/',
      '@openai/codex','@google/gemini-cli','@tencent-ai/codebuddy-code')
    & $npm.Source @arguments | Out-Host
    if($LASTEXITCODE -ne 0){throw ('AI CLI 自动安装失败，npm 错误码 '+$LASTEXITCODE)}
    Refresh-Path
    if(-not (Tools-Ready)){throw 'AI CLI 安装结束但缺少可执行程序'}
}
function Check-Only {
    Refresh-Path
    $info=[ordered]@{
       schema_version=1; windows_build=[Environment]::OSVersion.Version.Build;
       wsl=(WSL-Installed); docker=[bool](Docker-App);
       node=(Node-Ready); ai_clis=(Tools-Ready);
    }
    Write-Output ('WEIGUANG_DEPENDENCIES '+($info | ConvertTo-Json -Compress))
}
try{
    if($Mode -eq 'Check'){Check-Only;exit 0}
    if($Mode -eq 'WSLOnly'){
        if(-not (Is-Administrator)){throw 'WSLOnly 需要管理员权限'}
        $wsl=Join-Path $env:windir 'System32\wsl.exe'
        $proc=Start-Process -FilePath $wsl -ArgumentList @('--install','--no-distribution') -Wait -PassThru -NoNewWindow
        exit $proc.ExitCode
    }
    if([Environment]::OSVersion.Version.Build -lt 19041){
        throw 'Windows 版本太旧，WSL2 需要 Windows 10 2004 或 Windows 11'
    }
    if([Environment]::Is64BitOperatingSystem -ne $true){
        throw '此安装器只支持 Windows x64'
    }
    Save-State 'initializing' 'installing' $false
    Install-WSL
    Save-State 'docker' 'installing' $script:rebootRequired
    Install-Docker
    Save-State 'node' 'installing' $script:rebootRequired
    Install-Node
    Save-State 'ai-cli' 'installing' $script:rebootRequired
    Install-ModelCLIs
    if($script:rebootRequired){
        Save-State 'reboot' 'reboot_required' $true
        Message 'complete' '组件下载完成；请重启 Windows，再打开微光数学继续运行环境初始化'
        exit 3010
    }
    Save-State 'complete' 'ready' $false
    Message 'complete' '本机 WSL2、Docker Desktop、Node.js 与三个 AI CLI 已准备'
    exit 0
}catch{
    $message=[string]$_.Exception.Message
    if($message.Length -gt 240){$message=$message.Substring(0,240)}
    Message 'error' $message
    Save-State 'failed' 'retry_required' $script:rebootRequired
    exit 2
}
