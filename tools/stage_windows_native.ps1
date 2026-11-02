# Build-time staging for a self-contained Windows runtime.
# Native binaries reside INSIDE the setup EXE. No Docker Desktop or WSL2.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$payload = Join-Path $root 'desktop/native_runtime'
$engine = Join-Path $payload 'engine'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
if (Test-Path $engine) { Remove-Item $engine -Recurse -Force }
$packages = @('python=3.11', 'pip', 'postgresql=17.11', 'ffmpeg', 'pango', 'cairo', 'pycairo', 'manimpango', 'pkg-config')
& micromamba create --yes --strict-channel-priority --channel conda-forge --prefix $engine @packages
if ($LASTEXITCODE -ne 0) { throw 'MICROMAMBA_NATIVE_ENVIRONMENT_FAILED' }
$python = Join-Path $engine 'python.exe'
if (!(Test-Path $python)) { throw 'NATIVE_PYTHON_MISSING' }
Push-Location $root
try {
  & $python -m pip install --no-cache-dir --disable-pip-version-check './teacher_module' './visual_director' './animation_engine[render,speech]' './backend'
  if ($LASTEXITCODE -ne 0) { throw 'PYTHON_DEPENDENCY_INSTALL_FAILED' }
  & $python -m pip check
  if ($LASTEXITCODE -ne 0) { throw 'PYTHON_DEPENDENCY_CONFLICT' }
  & $python -c 'import fastapi, psycopg, manim, edge_tts, sympy; print("WINDOWS_NATIVE_PYTHON_OK")'
  if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_NATIVE_PYTHON_IMPORT_FAILED' }
} finally { Pop-Location }
$bin = Join-Path $engine 'Library/bin'
foreach ($name in @('initdb.exe', 'pg_ctl.exe', 'psql.exe', 'createdb.exe', 'ffmpeg.exe')) {
  $choices = @((Join-Path $bin $name), (Join-Path $engine $name), (Join-Path (Join-Path $engine 'Scripts') $name))
  $found = $choices | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (!$found) { throw "NATIVE_BINARY_MISSING: $name" }
}
# MiKTeX remains in the installer and is silently initialized in user data.
$texPath = Join-Path $payload 'basic-miktex-25.12-x64.exe'
$texUrl = 'https://mirror.ctan.org/systems/win32/miktex/setup/windows-x64/basic-miktex-25.12-x64.exe'
Invoke-WebRequest -Uri $texUrl -OutFile $texPath -MaximumRedirection 8
$expected = '14b42dd9f4b4a7813a8bfd69c8f99316c2888cc4ee26f631f397e163d85d6c62'
$actual = (Get-FileHash $texPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
  Remove-Item $texPath -Force
  throw "MIKTEX_BINARY_HASH_MISMATCH: $actual"
}
Write-Output 'FULL_WINDOWS_NATIVE_RUNTIME_STAGED'
