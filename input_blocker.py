#!/usr/bin/env python3
"""
input_blocker.py - Linux X11 입력장치 차단 스크립트

XGrabKeyboard / XGrabPointer를 사용하여 마우스, 키보드 이벤트를
sudo 없이 차단합니다. X11 세션에서 동작합니다.

사용법:
    python3 input_blocker.py --list
    python3 input_blocker.py --block-all [--timeout 10]
    python3 input_blocker.py --block keyboard [--timeout 10]
    python3 input_blocker.py --block mouse [--timeout 10]
    python3 input_blocker.py --block keyboard mouse [--timeout 10]
"""

import argparse
import signal
import subprocess
import sys
import time

try:
    from Xlib import X, display as xdisplay
    from Xlib.error import DisplayConnectionError
except ImportError:
    print("오류: python-xlib 라이브러리가 설치되어 있지 않습니다.")
    print("설치 명령: pip install python-xlib")
    sys.exit(1)

# XGrabKeyboard / XGrabPointer 성공 코드
_GRAB_SUCCESS = 0
_GRAB_STATUS = {
    0: "GrabSuccess",
    1: "AlreadyGrabbed",
    2: "GrabInvalidTime",
    3: "GrabNotViewable",
    4: "GrabFrozen",
}


def open_display() -> tuple:
    """X11 디스플레이와 루트 윈도우를 반환합니다."""
    try:
        dpy = xdisplay.Display()
    except DisplayConnectionError:
        print("오류: X11 디스플레이에 연결할 수 없습니다.")
        print("DISPLAY 환경변수를 확인하세요. (현재: " + str(__import__("os").environ.get("DISPLAY", "미설정")) + ")")
        sys.exit(1)
    root = dpy.screen().root
    return dpy, root


def list_devices_info():
    """연결된 X11 입력장치 목록을 출력합니다."""
    # xinput 명령으로 장치 목록 출력 (없으면 기본 안내)
    try:
        result = subprocess.run(
            ["xinput", "list", "--short"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            print("[X11 입력장치 목록]")
            print(result.stdout.rstrip())
        else:
            print("xinput 명령 실패:", result.stderr.strip())
    except FileNotFoundError:
        print("xinput을 찾을 수 없습니다. 설치: sudo apt install xinput")
    except subprocess.TimeoutExpired:
        print("xinput 명령 타임아웃")

    print()
    print("[차단 가능 대상]")
    print("  keyboard  - X11 키보드 전체")
    print("  mouse     - X11 포인터(마우스/터치패드) 전체")


def grab_keyboard(dpy, root) -> bool:
    """키보드를 독점 점유합니다."""
    status = root.grab_keyboard(
        owner_events=False,
        pointer_mode=X.GrabModeAsync,
        keyboard_mode=X.GrabModeAsync,
        time=X.CurrentTime,
    )
    dpy.flush()
    if status == _GRAB_SUCCESS:
        print("  [차단됨] keyboard")
        return True
    print(f"  [실패] keyboard: {_GRAB_STATUS.get(status, status)}")
    return False


def grab_pointer(dpy, root) -> bool:
    """마우스(포인터)를 독점 점유합니다."""
    status = root.grab_pointer(
        owner_events=False,
        event_mask=0,  # 이벤트를 어디에도 전달하지 않음
        pointer_mode=X.GrabModeAsync,
        keyboard_mode=X.GrabModeAsync,
        confine_to=X.NONE,
        cursor=X.NONE,
        time=X.CurrentTime,
    )
    dpy.flush()
    if status == _GRAB_SUCCESS:
        print("  [차단됨] mouse")
        return True
    print(f"  [실패] mouse: {_GRAB_STATUS.get(status, status)}")
    return False


def ungrab_all(dpy, keyboard: bool, mouse: bool):
    """점유한 장치를 해제합니다."""
    if keyboard:
        dpy.ungrab_keyboard(X.CurrentTime)
        print("  [해제됨] keyboard")
    if mouse:
        dpy.ungrab_pointer(X.CurrentTime)
        print("  [해제됨] mouse")
    dpy.flush()


def block_devices(targets: list[str], timeout: int | None):
    """지정된 대상을 차단하고 timeout 또는 Ctrl+C까지 유지합니다."""
    do_keyboard = "keyboard" in targets
    do_mouse = "mouse" in targets

    dpy, root = open_display()
    grabbed_keyboard = False
    grabbed_mouse = False

    print("\n장치 차단 시작...")
    if do_keyboard:
        grabbed_keyboard = grab_keyboard(dpy, root)
    if do_mouse:
        grabbed_mouse = grab_pointer(dpy, root)

    if not grabbed_keyboard and not grabbed_mouse:
        print("차단된 장치가 없습니다.")
        dpy.close()
        return

    total = sum([grabbed_keyboard, grabbed_mouse])
    print(f"\n총 {total}개 대상 차단됨.")
    if timeout:
        print(f"{timeout}초 후 자동 해제됩니다. (Ctrl+C로 즉시 해제)")
    else:
        print("Ctrl+C를 눌러 차단을 해제합니다.")

    interrupted = False

    def on_signal(signum, frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        if timeout:
            start = time.time()
            while not interrupted:
                elapsed = time.time() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    print(f"\n타임아웃 ({timeout}초) 도달. 차단 해제 중...")
                    break
                print(f"\r남은 시간: {remaining:.0f}초   ", end="", flush=True)
                time.sleep(0.5)
            print()
        else:
            while not interrupted:
                time.sleep(0.2)
            print("\nCtrl+C 감지. 차단 해제 중...")
    finally:
        ungrab_all(dpy, grabbed_keyboard, grabbed_mouse)
        dpy.close()
        print("모든 장치 차단이 해제되었습니다.")


def main():
    parser = argparse.ArgumentParser(
        description="Linux X11 입력장치 차단 스크립트 (XGrab 방식, sudo 불필요)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python3 input_blocker.py --list
  python3 input_blocker.py --block-all --timeout 10
  python3 input_blocker.py --block keyboard
  python3 input_blocker.py --block mouse --timeout 5
  python3 input_blocker.py --block keyboard mouse
        """,
    )
    parser.add_argument("--list", action="store_true", help="연결된 입력장치 목록 출력")
    parser.add_argument("--block-all", action="store_true", help="키보드 + 마우스 전체 차단")
    parser.add_argument(
        "--block",
        nargs="+",
        metavar="TARGET",
        choices=["keyboard", "mouse"],
        help="차단 대상 선택: keyboard / mouse (복수 지정 가능)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="자동 해제 시간(초). 미지정 시 Ctrl+C로만 해제",
    )

    args = parser.parse_args()

    if args.list:
        list_devices_info()
        return

    if not args.block_all and not args.block:
        parser.print_help()
        return

    targets = ["keyboard", "mouse"] if args.block_all else list(set(args.block))
    block_devices(targets, args.timeout)


if __name__ == "__main__":
    main()
