#!/usr/bin/env python3
"""
input_blocker.py - Linux X11 입력장치 차단 라이브러리 & CLI

XGrabKeyboard / XGrabPointer를 사용하여 마우스, 키보드 이벤트를
sudo 없이 차단합니다. X11 세션에서 동작합니다.

라이브러리 사용 예:
    from input_blocker import InputBlocker

    blocker = InputBlocker()
    blocker.block(keyboard=True, mouse=True)
    # ... 작업 ...
    blocker.unblock()

    # context manager
    with InputBlocker(keyboard=True, timeout=5):
        pass

CLI 사용 예:
    python3 input_blocker.py --list
    python3 input_blocker.py --block-all --timeout 10
    python3 input_blocker.py --block keyboard
    python3 input_blocker.py --block mouse --timeout 5
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

try:
    from Xlib import X, display as xdisplay
    from Xlib.error import DisplayConnectionError
    from Xlib.ext import xinput as xi
except ImportError:
    raise ImportError(
        "python-xlib 라이브러리가 필요합니다. 설치: pip install python-xlib"
    )

_GRAB_SUCCESS = 0
_GRAB_STATUS = {
    0: "GrabSuccess",
    1: "AlreadyGrabbed",
    2: "GrabInvalidTime",
    3: "GrabNotViewable",
    4: "GrabFrozen",
}
_USE_LABEL = {
    1: "MasterPointer",
    2: "MasterKeyboard",
    3: "SlavePointer",
    4: "SlaveKeyboard",
    5: "FloatingSlave",
}


class InputBlocker:
    """
    X11 입력장치(키보드/마우스)를 grab 방식으로 차단하는 클래스.

    Parameters
    ----------
    keyboard : bool
        키보드 차단 여부 (기본값: False)
    mouse : bool
        마우스(포인터) 차단 여부 (기본값: False)
    timeout : int | None
        자동 해제 시간(초). None이면 unblock() 호출 전까지 유지.

    Examples
    --------
    # 직접 호출
    blocker = InputBlocker(keyboard=True, mouse=True)
    blocker.block()
    blocker.unblock()

    # context manager (with 블록 종료 시 자동 해제)
    with InputBlocker(keyboard=True, timeout=5) as b:
        print(b.is_blocking)
    """

    def __init__(
        self,
        keyboard: bool = False,
        mouse: bool = False,
        timeout: int | None = None,
    ):
        self.keyboard = keyboard
        self.mouse = mouse
        self.timeout = timeout

        self._dpy = None
        self._root = None
        self._grabbed_keyboard = False
        self._grabbed_mouse = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_blocking(self) -> bool:
        """현재 차단 중인지 여부."""
        return self._grabbed_keyboard or self._grabbed_mouse

    def block(self) -> dict[str, bool]:
        """
        설정된 대상을 차단합니다.

        Returns
        -------
        dict
            {'keyboard': bool, 'mouse': bool} — 각 대상의 차단 성공 여부.

        Raises
        ------
        RuntimeError
            이미 차단 중이거나 X11 연결 실패 시.
        """
        if self.is_blocking:
            raise RuntimeError("이미 차단 중입니다. unblock() 후 다시 호출하세요.")
        if not self.keyboard and not self.mouse:
            raise ValueError("keyboard 또는 mouse 중 하나 이상을 True로 설정해야 합니다.")

        self._dpy, self._root = self._open_display()

        if self.keyboard:
            self._grabbed_keyboard = self._grab_keyboard()
        if self.mouse:
            self._grabbed_mouse = self._grab_pointer()

        return {"keyboard": self._grabbed_keyboard, "mouse": self._grabbed_mouse}

    def unblock(self):
        """차단을 해제합니다. 차단 중이 아니면 아무 동작도 하지 않습니다."""
        if not self._dpy:
            return
        if self._grabbed_keyboard:
            self._dpy.ungrab_keyboard(X.CurrentTime)
            self._grabbed_keyboard = False
        if self._grabbed_mouse:
            self._dpy.ungrab_pointer(X.CurrentTime)
            self._grabbed_mouse = False
        self._dpy.flush()
        self._dpy.close()
        self._dpy = None
        self._root = None

    def block_and_wait(self):
        """
        차단 후 timeout 또는 SIGINT/SIGTERM까지 대기합니다.
        CLI에서 사용하는 blocking 루프.
        """
        result = self.block()
        grabbed = [k for k, v in result.items() if v]
        if not grabbed:
            return result

        interrupted = False

        def on_signal(signum, frame):
            nonlocal interrupted
            interrupted = True

        prev_sigint = signal.signal(signal.SIGINT, on_signal)
        prev_sigterm = signal.signal(signal.SIGTERM, on_signal)

        try:
            if self.timeout:
                start = time.time()
                while not interrupted:
                    remaining = self.timeout - (time.time() - start)
                    if remaining <= 0:
                        break
                    print(f"\r남은 시간: {remaining:.0f}초   ", end="", flush=True)
                    time.sleep(0.5)
                print()
            else:
                while not interrupted:
                    time.sleep(0.2)
        finally:
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            self.unblock()

        return result

    @staticmethod
    def list_devices() -> list[dict]:
        """
        연결된 X11 입력장치 목록을 반환합니다.

        Returns
        -------
        list of dict
            [{'id': int, 'name': str, 'use': int, 'type': str}, ...]
        """
        dpy, _ = InputBlocker._open_display()
        try:
            info = dpy.xinput_query_device(xi.AllDevices)
            return [
                {
                    "id": d.deviceid,
                    "name": d.name,
                    "use": d.use,
                    "type": _USE_LABEL.get(d.use, f"use={d.use}"),
                }
                for d in sorted(info.devices, key=lambda d: d.deviceid)
            ]
        finally:
            dpy.close()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> InputBlocker:
        self.block()
        return self

    def __exit__(self, *_):
        self.unblock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_display():
        try:
            dpy = xdisplay.Display()
        except DisplayConnectionError:
            display_val = os.environ.get("DISPLAY", "미설정")
            raise RuntimeError(
                f"X11 디스플레이에 연결할 수 없습니다. DISPLAY={display_val}"
            )
        return dpy, dpy.screen().root

    def _grab_keyboard(self) -> bool:
        status = self._root.grab_keyboard(
            owner_events=False,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            time=X.CurrentTime,
        )
        self._dpy.flush()
        return status == _GRAB_SUCCESS

    def _grab_pointer(self) -> bool:
        status = self._root.grab_pointer(
            owner_events=False,
            event_mask=0,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            confine_to=X.NONE,
            cursor=X.NONE,
            time=X.CurrentTime,
        )
        self._dpy.flush()
        return status == _GRAB_SUCCESS


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _cli_list():
    devices = InputBlocker.list_devices()
    print(f"{'ID':<5} {'유형':<20} {'이름'}")
    print("-" * 60)
    for d in devices:
        print(f"{d['id']:<5} {d['type']:<20} {d['name']}")
    print()
    print("[차단 가능 대상]")
    print("  keyboard  - X11 키보드 전체 (MasterKeyboard)")
    print("  mouse     - X11 포인터(마우스/터치패드) 전체 (MasterPointer)")


def _cli_block(targets: list[str], timeout: int | None):
    blocker = InputBlocker(
        keyboard="keyboard" in targets,
        mouse="mouse" in targets,
        timeout=timeout,
    )

    print("\n장치 차단 시작...")
    result = blocker.block()
    for target, ok in result.items():
        if (target == "keyboard" and blocker.keyboard) or (target == "mouse" and blocker.mouse):
            status = "차단됨" if ok else f"실패 ({_GRAB_STATUS.get(1, '알 수 없음')})"
            print(f"  [{status}] {target}")

    grabbed = [k for k, v in result.items() if v]
    if not grabbed:
        print("차단된 장치가 없습니다.")
        return

    print(f"\n총 {len(grabbed)}개 대상 차단됨.")
    if timeout:
        print(f"{timeout}초 후 자동 해제됩니다. (Ctrl+C로 즉시 해제)")
    else:
        print("Ctrl+C를 눌러 차단을 해제합니다.")

    # block() 이미 호출했으므로 대기 루프만 직접 실행
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
                remaining = timeout - (time.time() - start)
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
        blocker.unblock()
        for target in grabbed:
            print(f"  [해제됨] {target}")
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
        _cli_list()
        return

    if not args.block_all and not args.block:
        parser.print_help()
        return

    targets = ["keyboard", "mouse"] if args.block_all else list(set(args.block))
    _cli_block(targets, args.timeout)


if __name__ == "__main__":
    main()
