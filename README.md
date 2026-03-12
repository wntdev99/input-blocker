# input-blocker

Linux X11 환경에서 키보드/마우스 입력을 **sudo 없이** 차단하는 Python 스크립트입니다.
`XGrabKeyboard` / `XGrabPointer` X11 API를 사용하여 독점 점유 방식으로 이벤트를 차단합니다.

## 활용 사례
- 키오스크 모드 입력 잠금
- 프레젠테이션 중 실수 입력 방지
- 어린이 화면 잠금
- 자동화 테스트 중 입력 간섭 방지

## 요구사항
- Python 3.7+
- X11 세션 (`echo $XDG_SESSION_TYPE` → `x11`)
- `python-xlib` (외부 시스템 패키지 불필요 — `xinput` 명령 미사용)

```bash
pip install python-xlib
```

## 라이브러리 사용법

```python
from input_blocker import InputBlocker

# 직접 호출
blocker = InputBlocker(keyboard=True, mouse=True)
blocker.block()
# ... 작업 ...
blocker.unblock()

# context manager (with 블록 종료 시 자동 해제)
with InputBlocker(keyboard=True, timeout=5):
    pass

# 차단 상태 확인
blocker = InputBlocker(keyboard=True)
blocker.block()
print(blocker.is_blocking)  # True
blocker.unblock()

# 연결된 장치 목록 조회
devices = InputBlocker.list_devices()
for d in devices:
    print(d['id'], d['type'], d['name'])
```

## CLI 사용법

```bash
# 연결된 입력장치 목록 확인
python3 input_blocker.py --list

# 키보드 + 마우스 전체 차단 (Ctrl+C로 해제)
python3 input_blocker.py --block-all

# 키보드만 5초 차단 후 자동 해제
python3 input_blocker.py --block keyboard --timeout 5

# 마우스만 차단
python3 input_blocker.py --block mouse --timeout 10

# 키보드 + 마우스 동시 차단
python3 input_blocker.py --block keyboard mouse --timeout 30
```

## 옵션

| 옵션 | 설명 |
|------|------|
| `--list` | X11 입력장치 목록 출력 |
| `--block-all` | 키보드 + 마우스 전체 차단 |
| `--block keyboard\|mouse` | 지정 대상만 차단 (복수 지정 가능) |
| `--timeout SECONDS` | 자동 해제 시간(초). 미지정 시 Ctrl+C까지 유지 |

## 전역 설치 방법

프로젝트 디렉토리를 클론한 후, 환경에 맞는 방법을 선택합니다.

```bash
git clone https://github.com/wntdev99/input-blocker
cd input-blocker
pip install python-xlib  # 의존성 설치
```

---

### 방법 1 — pip 설치 (권장)

pip 20.0 이상 환경에서 동작합니다.

```bash
pip install -e .
```

설치 후 어디서든 import 및 CLI 명령 사용 가능:

```python
from input_blocker import InputBlocker
```

```bash
input-blocker --list
```

---

### 방법 2 — PYTHONPATH (pip 없이, 영구 적용)

pip가 없거나 시스템 pip가 손상된 환경에서 사용합니다.

```bash
echo 'export PYTHONPATH="/path/to/input-blocker:$PYTHONPATH"' >> ~/.bashrc
source ~/.bashrc
```

---

### 방법 3 — .pth 파일 (root 환경 권장)

root 계정이거나 pip가 완전히 동작하지 않는 환경에서 가장 안정적입니다.

```bash
echo "/path/to/input-blocker" > /usr/local/lib/python3.x/dist-packages/input_blocker.pth
```

`python3.x`는 실제 버전으로 치환합니다:

```bash
# 버전 확인
python3 -c "import sys; print(sys.version)"

# 예시 (Python 3.8)
echo "/root/lib/input-blocker" > /usr/local/lib/python3.8/dist-packages/input_blocker.pth
```

---

### 설치 확인

```bash
python3 -c "from input_blocker import InputBlocker; print('OK')"
```

---

## 동작 원리

| 단계 | 내용 |
|------|------|
| 차단 | `XGrabKeyboard` / `XGrabPointer` 호출로 X11 루트 윈도우가 입력을 독점 점유 |
| 이벤트 처리 | `event_mask=0` 으로 점유된 이벤트를 어느 윈도우에도 전달하지 않음 |
| 해제 | `ungrab_keyboard` / `ungrab_pointer` 호출로 정상 복원 |

> **참고**: sudo 또는 `input` 그룹 권한이 불필요합니다.
> Wayland 세션은 지원하지 않습니다.

## 테스트 방법

```bash
# 1. 터미널에서 5초 키보드 차단 실행
python3 input_blocker.py --block keyboard --timeout 5

# 2. 차단 중 다른 창에서 키 입력 시도 → 입력 안 됨
# 3. 5초 후 자동 해제 → 정상 입력 복원
```
