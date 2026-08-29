# Windows 포터블 Blender에서 CatTools 전용 개발 환경을 실행합니다.
[CmdletBinding()]
param(
    # blender.exe와 portable 폴더를 둘 전용 Blender 경로입니다.
    [string]$BlenderDir = "D:\Tools\Blender-5.2-CatToolsDev",

    # 사용하는 Blender 버전을 로그와 설치 안내에 표시합니다.
    [string]$Version = "5.2",

    # Junction만 준비하고 Blender는 실행하지 않습니다.
    [switch]$LinkOnly,

    # Blender를 GUI 없이 실행합니다.
    [switch]$Background,

    # 개발 확장 활성화 후 실행할 Python 표현식입니다.
    [string]$PythonExpr,

    # 개발 확장 활성화 후 실행할 Python 파일입니다.
    [string]$PythonFile
)

$ErrorActionPreference = 'Stop'

$AddonId = 'cat_tools'
$ModuleName = 'bl_ext.user_default.cat_tools'
$SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ManifestPath = Join-Path $SourceDir 'blender_manifest.toml'
$BootstrapScript = Join-Path $SourceDir 'scripts\dev_bootstrap.py'
$BlenderExecutable = Join-Path $BlenderDir 'blender.exe'

if (-not (Test-Path -LiteralPath $BlenderExecutable -PathType Leaf)) {
    Write-Error @"
CatTools 전용 포터블 Blender를 찾을 수 없습니다: $BlenderExecutable

Blender $Version 포터블 ZIP을 다음 기본 경로에 압축 해제하거나
-BlenderDir 매개변수로 다른 경로를 지정하세요: $BlenderDir
"@
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    Write-Error "CatTools 매니페스트를 찾을 수 없습니다: $ManifestPath"
}

$ManifestText = Get-Content -LiteralPath $ManifestPath -Raw
if ($ManifestText -notmatch '(?m)^\s*id\s*=\s*"cat_tools"\s*$') {
    Write-Error "매니페스트 id가 AddonId와 일치하지 않습니다: $AddonId"
}

if ($PythonExpr -and $PythonFile) {
    Write-Error '-PythonExpr와 -PythonFile은 동시에 사용할 수 없습니다.'
}

if ($PythonFile) {
    if (-not (Test-Path -LiteralPath $PythonFile -PathType Leaf)) {
        Write-Error "Python 파일을 찾을 수 없습니다: $PythonFile"
    }
    $PythonFile = (Resolve-Path -LiteralPath $PythonFile).Path
}

$PortableRoot = Join-Path $BlenderDir 'portable'
$ExtensionDir = Join-Path $PortableRoot 'extensions\user_default'
$AddonLink = Join-Path $ExtensionDir $AddonId
New-Item -ItemType Directory -Path $ExtensionDir -Force | Out-Null

$ExistingItem = Get-Item -LiteralPath $AddonLink -Force -ErrorAction SilentlyContinue
if ($null -ne $ExistingItem) {
    $IsSupportedLink = $ExistingItem.LinkType -in @('Junction', 'SymbolicLink')
    if (-not $IsSupportedLink) {
        Write-Error @"
개발 확장 경로에 실제 폴더 또는 파일이 있습니다: $AddonLink

사용자 파일을 보호하기 위해 자동으로 삭제하지 않습니다.
해당 항목을 직접 옮긴 뒤 다시 실행하세요.
"@
    }

    $CurrentTarget = @($ExistingItem.Target)[0]
    $ResolvedTarget = $null
    if ($CurrentTarget) {
        if (-not [System.IO.Path]::IsPathRooted($CurrentTarget)) {
            $CurrentTarget = Join-Path $ExistingItem.Parent.FullName $CurrentTarget
        }
        $ResolvedTarget = Resolve-Path -LiteralPath $CurrentTarget -ErrorAction SilentlyContinue
    }

    $TargetMatches = $null -ne $ResolvedTarget -and [string]::Equals(
        $ResolvedTarget.Path.TrimEnd('\'),
        $SourceDir.TrimEnd('\'),
        [System.StringComparison]::OrdinalIgnoreCase
    )

    if ($TargetMatches) {
        Write-Host "Junction 유지: $AddonLink -> $SourceDir"
    } else {
        Write-Host "잘못된 개발 링크를 CatTools 저장소로 다시 연결합니다."
        # 링크 자체만 제거하며 링크 대상의 파일은 삭제하지 않습니다.
        if ($ExistingItem.PSIsContainer) {
            [System.IO.Directory]::Delete($AddonLink, $false)
        } else {
            [System.IO.File]::Delete($AddonLink)
        }
        New-Item -ItemType Junction -Path $AddonLink -Target $SourceDir | Out-Null
        Write-Host "Junction 완료: $AddonLink -> $SourceDir"
    }
} else {
    New-Item -ItemType Junction -Path $AddonLink -Target $SourceDir | Out-Null
    Write-Host "Junction 완료: $AddonLink -> $SourceDir"
}

Write-Host "포터블 프로필: $PortableRoot"
Write-Host "개발 확장:     $ModuleName"

if ($LinkOnly) {
    Write-Host '연결만 완료했습니다. 실행하려면 -LinkOnly 없이 다시 호출하세요.'
    exit 0
}

$BlenderArguments = @('--python-exit-code', '1')
if ($Background) {
    $BlenderArguments += '--background'
}
$BlenderArguments += @('--python', $BootstrapScript)

if ($PythonFile) {
    $BlenderArguments += @('--python', $PythonFile)
} elseif ($PythonExpr) {
    $BlenderArguments += @('--python-expr', $PythonExpr)
}

if ($Background) {
    Write-Host "백그라운드 Blender 실행: $BlenderExecutable"
} else {
    Write-Host "개발 Blender 실행: $BlenderExecutable"
}

& $BlenderExecutable @BlenderArguments
exit $LASTEXITCODE
