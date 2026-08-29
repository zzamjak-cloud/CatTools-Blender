# CatTools

CatTools는 CAT 블록 모델링 작업에 사용해 온 **Woody Tools**의 최신 설치본을 정리해 이전한 Blender Extension입니다. 첫 공개 버전은 기존 작업 흐름과 파일 호환성을 우선하여 기존 연산자 식별자(`bl_idname`)를 유지합니다.

## 요구 사항

- Blender 4.2 이상
- CatTools 1.0.0

## 제공 기능

- 기본 머티리얼 생성
- 양면 텍스처 및 2·3·4 텍스처 셰이더 구성
- 선택 오브젝트의 원형 배열
- 래티스 생성 및 연결
- X·Y·Z 미러 모디파이어 추가

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

```bash
python3 scripts/build_extension.py
```

생성된 `dist/cat_tools-v1.0.0.zip`은 릴리스와 원격 저장소 생성에 사용하는 개발용 패키지입니다.

## 검사

```bash
python3 -m unittest discover -s tests -v
```

검사는 Python 문법, Extension 매니페스트, 등록 클래스 순서, 기존 `bl_idname` 호환성을 확인합니다. 첫 릴리스는 Blender 5.2 LTS에서 등록·해제와 등록 연산자 10개 실행을 검증했습니다.

## 라이선스

GPL-3.0-or-later. 자세한 내용은 [LICENSE](LICENSE)를 확인하세요.
