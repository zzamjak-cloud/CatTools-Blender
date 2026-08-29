#!/bin/zsh
# macOS에서 기본 Blender 설정과 분리된 CatTools 개발 프로필을 실행합니다.
set -euo pipefail

BLENDER_BIN="${BLENDER_BIN:-/Applications/Blender.app/Contents/MacOS/Blender}"
BLENDER_VERSION="${BLENDER_VERSION:-5.2}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_BASE="${CATTOOLS_DEV_PROFILE_BASE:-$HOME/Library/Application Support/Blender/CatToolsBlenderDev}"
PROFILE="$PROFILE_BASE/$BLENDER_VERSION"
EXTENSION_DIR="$PROFILE/extensions/user_default"
ADDON_LINK="$EXTENSION_DIR/cat_tools"
BOOTSTRAP_SCRIPT="$REPO_ROOT/scripts/dev_bootstrap.py"

if [[ ! -x "$BLENDER_BIN" ]]; then
    print -u2 "Blender 실행 파일을 찾을 수 없습니다: $BLENDER_BIN"
    print -u2 "BLENDER_BIN 환경변수로 설치 경로를 지정하세요."
    exit 1
fi

if [[ -e "$ADDON_LINK" && ! -L "$ADDON_LINK" ]]; then
    print -u2 "개발 확장 경로에 심링크가 아닌 항목이 있습니다: $ADDON_LINK"
    print -u2 "해당 항목을 직접 확인한 뒤 다시 실행하세요."
    exit 1
fi

mkdir -p "$EXTENSION_DIR"
ln -sfn "$REPO_ROOT" "$ADDON_LINK"

export BLENDER_VERSION
export CATTOOLS_DEV_PROFILE_BASE="$PROFILE_BASE"
export BLENDER_USER_RESOURCES="$PROFILE"

print "격리 프로필: $BLENDER_USER_RESOURCES"
print "소스 링크:   $ADDON_LINK -> $REPO_ROOT"

# 최종 실행 전에 격리 프로필에서 개발 확장을 활성화하고 설정을 저장합니다.
"$BLENDER_BIN" --background --python-exit-code 1 --python "$BOOTSTRAP_SCRIPT"

exec "$BLENDER_BIN" --python-exit-code 1 "$@"
