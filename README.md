# CatTools

CatTools는 CAT 블록 모델링 작업에 사용해 온 **Woody Tools**의 최신 설치본을 정리해 이전한 Blender Extension입니다. 첫 공개 버전은 기존 작업 흐름과 파일 호환성을 우선하여 기존 연산자 식별자(`bl_idname`)를 유지합니다.

## 요구 사항

- Blender 4.2 이상
- CatTools 1.0.3

## 제공 기능

- N 키 사이드바 단축키: 사이드바를 열 때 CatTools 탭을 활성 탭으로 지정 (사이드바가 열린 상태로 저장된 파일도 파일 로드 시 CatTools 탭으로 복원). 탭 목록에서 Item·Tool·View는 Blender 내부에 정의되어 있어 CatTools를 그 위로 옮길 수는 없고, 활성 탭만 지정한다.
- Transform 축약 필드: Loc·Rot·Sca를 각각 한 줄 3열 그리드로 표시하며, 사이드바가 좁아지면 라벨을 L·R·S로 축약
- Align 축약 버튼: 활성 오브젝트를 기준으로 선택 오브젝트의 Loc·Rot·Sca를 X·Y·Z·All 축별 정렬
- 기본 머티리얼 생성
- 양면 텍스처 및 2·3·4 텍스처 셰이더 구성
- Catoon 셀셰이딩 머티리얼: 텍스처 색감을 유지한 2톤 만화풍 그림자 (Shadow Color·Threshold·Softness 조절, Shader to RGB 기반이라 EEVEE 전용). Image Texture 노드에 흰색 기본 이미지가 들어가 있으므로, 여기에 사용할 텍스처를 지정한다.
- 선택 오브젝트의 원형 배열
- 래티스 생성 및 연결
- X축은 왼쪽 영역을 보존하고 오른쪽 영역을 정리한 뒤 미러 모디파이어 추가
- Y·Z축은 양수 영역을 보존하고 음수 영역을 정리한 뒤 미러 모디파이어 추가

과거 스크립트에 있었지만 등록 목록에서 주석 처리된 실험 기능은 이번 버전에서도 노출하지 않습니다.

## 설치

### Woody Tools에서 전환

CatTools는 기존 Woody Tools의 연산자 식별자를 유지하므로 두 애드온을 동시에 활성화하면 등록 충돌이 발생합니다.

1. 작업 중인 Blender 파일을 저장합니다.
2. **Edit > Preferences > Add-ons**에서 `Woody Tools`를 비활성화합니다.
3. Blender를 종료한 뒤 다시 실행합니다.
4. 아래 절차로 CatTools를 설치하고 활성화합니다.
5. CatTools 동작을 확인한 뒤에만 기존 `ADDON_WoodyTools_0_2.py`를 제거합니다.

이전 Blender 버전의 Woody Tools 설치본과 Google Drive 원본은 자동으로 삭제하지 않습니다.

### 원격 저장소 설치

1. Blender에서 **Edit > Preferences > Get Extensions**를 엽니다.
2. **Repositories**에서 `+`를 누르고 **Add Remote Repository**를 선택합니다.
3. URL에 `https://zzamjak-cloud.github.io/CatTools-Blender/index.json`을 입력하고 저장소를 추가합니다.
4. 저장소를 동기화한 뒤 `CatTools`를 검색해 **Install**을 누릅니다.
5. 3D 뷰포트 사이드바의 **CatTools** 탭을 엽니다.

추후 업데이트를 자동으로 확인하려면 추가한 원격 저장소의 **Check for Updates on Startup**을 켭니다. 새 버전 알림이 표시되면 **Update** 또는 **Install Available Updates**로 갱신합니다.

### 개발 버전

#### macOS

macOS에서는 전용 `CatToolsBlenderDev/<Blender 버전>` 프로필로 개발 소스를 실행할 수 있습니다. 이 방식은 기본 Blender 프로필과 원격 설치본을 변경하지 않으며, 저장소 루트를 `extensions/user_default/cat_tools`에 심링크한 뒤 `bl_ext.user_default.cat_tools`를 자동으로 활성화합니다.

```bash
./scripts/dev_run.sh
```

기본값은 Blender 5.2와 `/Applications/Blender.app/Contents/MacOS/Blender`입니다. 다른 설치본은 환경변수로 지정하고, `--background`를 비롯한 Blender 인자는 명령 뒤에 그대로 전달합니다.
개발 실행기는 Python 시작 스크립트 오류를 종료 코드 1로 반환하므로 자동 검사에서 예외를 성공으로 오인하지 않습니다.

```bash
BLENDER_VERSION=5.3 BLENDER_BIN="/Applications/Blender 5.3.app/Contents/MacOS/Blender" ./scripts/dev_run.sh
./scripts/dev_run.sh --background
```

격리 프로필과 개발 확장 로드를 Blender에서 직접 확인하려면 다음 검사를 실행합니다.

```bash
./scripts/dev_run.sh --background --python tests/blender_dev_profile_smoke.py
```

개발 프로필에 로드된 실제 CatTools로 X/Y/Z Mirror와 등록·해제를 확인하려면 다음 검사를 실행합니다.

```bash
./scripts/dev_run.sh --background --python tests/blender_mirror_smoke.py
```

Align 연산자의 축별 정렬과 비오일러 rotation_mode 처리를 확인하려면 다음 검사를 실행합니다.

```bash
./scripts/dev_run.sh --background --python tests/blender_align_smoke.py
```

Catoon 셀셰이딩이 실제로 2톤으로 렌더링되는지 확인하려면 다음 검사를 실행합니다.

```bash
./scripts/dev_run.sh --background --python tests/blender_catoon_smoke.py
```

N 키 사이드바 토글과 CatTools 탭 활성화를 확인하려면 창이 필요하므로 `--background` 없이 실행합니다.

```bash
./scripts/dev_run.sh --python tests/blender_sidebar_smoke.py
```

기능 수정 중에는 이 개발 프로필을 사용하며 GitHub 릴리스나 원격 설치본을 매번 갱신할 필요가 없습니다.

#### Windows

Windows에서는 포터블 Blender 전용 경로를 사용해 일반 설치본과 개발 설정을 분리합니다. 기본 경로는 `D:\Tools\Blender-5.2-CatToolsDev`이며, 저장소 루트를 `portable\extensions\user_default\cat_tools`에 디렉터리 Junction으로 연결합니다. 실제 폴더가 이미 있으면 사용자 파일 보호를 위해 중단하고, 대상이 잘못된 Junction이나 심링크만 안전하게 다시 연결합니다.

PowerShell에서는 다음 명령으로 GUI 개발 환경을 실행합니다. 다른 위치의 포터블 Blender는 `-BlenderDir`로 지정할 수 있습니다.

```powershell
.\scripts\dev_run.ps1
.\scripts\dev_run.ps1 -BlenderDir "E:\Tools\Blender-5.2-CatToolsDev"
```

연결만 준비하거나 백그라운드에서 Python 검사·표현식을 실행할 수도 있습니다. 모든 Python 실행에는 `--python-exit-code 1`이 적용되며, 사용자 코드 전에 `bl_ext.user_default.cat_tools`를 활성화하는 공용 부트스트랩이 실행됩니다.

```powershell
.\scripts\dev_run.ps1 -LinkOnly
.\scripts\dev_run.ps1 -Background -PythonFile ".\tests\blender_dev_profile_smoke.py"
.\scripts\dev_run.ps1 -Background -PythonExpr "import bpy; print(bpy.app.version_string)"
```

명령 프롬프트에서는 같은 인자를 배치 래퍼로 전달합니다.

```bat
.\scripts\dev_run.bat -Background -PythonFile ".\tests\blender_mirror_smoke.py"
```

배포용 Extension 패키지는 다음 명령으로 생성합니다.

```bash
python3 scripts/build_extension.py
```

생성된 `dist/cat_tools-v1.0.3.zip`은 릴리스와 원격 저장소 생성에 사용하는 개발용 패키지입니다.

## 검사

```bash
python3 -m unittest discover -s tests -v
```

Blender가 설치된 환경에서는 실제 미러 동작도 확인할 수 있습니다.

```bash
blender --background --factory-startup --python tests/blender_mirror_smoke.py
```

사이드바 단축키 검사는 탭 목록이 그리기 단계에서 만들어지므로 창을 띄운 상태로 실행합니다.

```bash
blender --factory-startup --python-exit-code 1 --python tests/blender_sidebar_smoke.py
```

검사는 Python 문법, Extension 매니페스트, 등록 클래스 순서, 기존 `bl_idname` 호환성과 X·Y·Z 미러 방향을 확인합니다. 첫 릴리스는 Blender 5.2 LTS에서 등록·해제와 등록 연산자 10개 실행을 검증했습니다.

## 라이선스

GPL-3.0-or-later. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.
