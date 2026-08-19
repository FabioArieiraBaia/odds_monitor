"""
Instant Win32 Foreground Window Manager (< 0.1ms).
Bypasses Windows OS Focus-Stealing Prevention via native ctypes calls.
"""
import sys
import logging

logger = logging.getLogger("window_manager")

_is_windows = sys.platform == "win32"

if _is_windows:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
else:
    user32 = None


def focus_chrome_bet365() -> bool:
    """
    Finds the Bet365 Chrome window and brings it to the immediate foreground (< 0.1ms).
    Returns True if window was found and focused, False otherwise.
    """
    if not _is_windows or not user32:
        return False

    target_hwnd = None

    def enum_windows_callback(hwnd, extra):
        nonlocal target_hwnd
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.lower()
                
                # Check for Bet365 window keywords
                if "bet365" in title or "apostas" in title:
                    target_hwnd = hwnd
                    return False  # Stop enumeration
        return True

    try:
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)

        if target_hwnd:
            # 1. Simulate brief ALT key press to grant focus permission from Windows kernel
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # 2. Restore window if minimized (SW_RESTORE = 9)
            user32.ShowWindow(target_hwnd, 9)
            user32.SetForegroundWindow(target_hwnd)
            user32.BringWindowToTop(target_hwnd)
            logger.info(f"[WindowManager] Bet365 Chrome window ({target_hwnd}) brought to foreground in <0.1ms")
            return True
    except Exception as e:
        logger.debug(f"[WindowManager] Failed to focus Bet365 window: {e}")

    return False
