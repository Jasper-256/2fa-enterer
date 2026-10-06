"""Capture the configured screen area, recognize digits, and enter them on macOS."""
import ctypes as C
import json
import os
import sys
import time

os.environ.setdefault('OMP_THREAD_LIMIT', '1')
REGION = {'left': 674, 'top': 442, 'width': 162, 'height': 40}
TESSDATA = '/opt/homebrew/opt/tesseract/share/tessdata'
INVERT = bytes(255-value for value in range(256))


def bind(lib, name, result, *args):
    function = getattr(lib, name)
    function.restype = result
    function.argtypes = args
    return function


class Capture:
    """Capture Retina pixels and release every native image after copying it."""
    def __init__(self):
        from mss.darwin import CGRect
        from mss.screenshot import ScreenShot
        from mss.models import Size
        self.ScreenShot, self.Size, self.Rect = ScreenShot, Size, CGRect
        core = C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        foundation = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.capture = bind(core, 'CGWindowListCreateImage', C.c_void_p, CGRect, C.c_uint32, C.c_uint32, C.c_uint32)
        self.width = bind(core, 'CGImageGetWidth', C.c_size_t, C.c_void_p)
        self.height = bind(core, 'CGImageGetHeight', C.c_size_t, C.c_void_p)
        self.stride = bind(core, 'CGImageGetBytesPerRow', C.c_size_t, C.c_void_p)
        self.provider = bind(core, 'CGImageGetDataProvider', C.c_void_p, C.c_void_p)
        self.copy = bind(core, 'CGDataProviderCopyData', C.c_void_p, C.c_void_p)
        self.bytes = bind(foundation, 'CFDataGetBytePtr', C.c_void_p, C.c_void_p)
        self.length = bind(foundation, 'CFDataGetLength', C.c_long, C.c_void_p)
        self.release_data = bind(foundation, 'CFRelease', None, C.c_void_p)
        self.release_image = bind(core, 'CGImageRelease', None, C.c_void_p)

    def grab(self, region):
        rect = self.Rect((region['left'],region['top']), (region['width'],region['height']))
        # Ignore framing, force opaque, and retain native Retina resolution.
        image = self.capture(rect, 1, 0, 3)
        if not image:
            raise RuntimeError('Screen capture failed; check existing Screen Recording permission')
        data = None
        try:
            width, height = self.width(image), self.height(image)
            stride = self.stride(image)
            data = self.copy(self.provider(image))
            if not data:
                raise RuntimeError('Screen capture returned no pixel data')
            pixels = C.string_at(self.bytes(data),self.length(data))
            if stride != width*4:
                pixels = b''.join(pixels[row*stride:row*stride+width*4] for row in range(height))
            return self.ScreenShot(bytearray(pixels),region,size=self.Size(width,height))
        finally:
            if data:
                self.release_data(data)
            self.release_image(image)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


class OCR:
    def __init__(self):
        lib = C.CDLL('/opt/homebrew/lib/libtesseract.dylib')
        self.create = bind(lib, 'TessBaseAPICreate', C.c_void_p)
        self.delete = bind(lib, 'TessBaseAPIDelete', None, C.c_void_p)
        self.init = bind(lib, 'TessBaseAPIInit3', C.c_int, C.c_void_p, C.c_char_p, C.c_char_p)
        self.variable = bind(lib, 'TessBaseAPISetVariable', C.c_int, C.c_void_p, C.c_char_p, C.c_char_p)
        self.psm = bind(lib, 'TessBaseAPISetPageSegMode', None, C.c_void_p, C.c_int)
        self.image = bind(lib, 'TessBaseAPISetImage', None, C.c_void_p, C.c_char_p, C.c_int, C.c_int, C.c_int, C.c_int)
        self.text = bind(lib, 'TessBaseAPIGetUTF8Text', C.c_void_p, C.c_void_p)
        self.free_text = bind(lib, 'TessDeleteText', None, C.c_void_p)
        self.clear = bind(lib, 'TessBaseAPIClear', None, C.c_void_p)
        self.handle = self.create()
        if self.init(self.handle, TESSDATA.encode(), b'eng'):
            self.delete(self.handle)
            raise RuntimeError('Tesseract initialization failed')
        self.psm(self.handle, 7)
        self.variable(self.handle, b'tessedit_char_whitelist', b'0123456789')

    def digits(self, pixels, width, height, channels=3, stride=None):
        # Normalize dark backgrounds before OCR; automatic inversion can drop zeros.
        sample = pixels[::max(1,len(pixels)//64)]
        if sample and sum(sample)/len(sample) < 128:
            original = pixels
            pixels = pixels.translate(INVERT)
            if channels == 4:
                pixels = bytearray(pixels)
                pixels[3::4] = original[3::4]
                pixels = bytes(pixels)
        self.image(self.handle, pixels, width, height, channels, stride or width*channels)
        pointer = self.text(self.handle)
        if not pointer:
            self.clear(self.handle)
            return ''
        try:
            text = C.string_at(pointer).decode('utf-8')
            return ''.join(ch for ch in text if '0' <= ch <= '9')
        finally:
            self.free_text(pointer)
            self.clear(self.handle)

    def close(self):
        if self.handle:
            self.delete(self.handle)
            self.handle = None


def type_digits(text):
    """Press and release each digit key, leaving 2 ms between characters."""
    if not text:
        return
    core = C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    foundation = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    create = bind(core, 'CGEventCreateKeyboardEvent', C.c_void_p, C.c_void_p, C.c_uint16, C.c_bool)
    flags = bind(core, 'CGEventSetFlags', None, C.c_void_p, C.c_uint64)
    post = bind(core, 'CGEventPost', None, C.c_uint32, C.c_void_p)
    release = bind(foundation, 'CFRelease', None, C.c_void_p)
    create_source = bind(core, 'CGEventSourceCreate', C.c_void_p, C.c_int32)
    source = create_source(-1)  # Private state, independent of held Hyper modifiers.
    if not source:
        raise RuntimeError('Could not create keyboard event source')
    # Numeric keypad keys produce digits without depending on shifted number rows.
    keycodes = dict(zip('0123456789', (82, 83, 84, 85, 86, 87, 88, 89, 91, 92)))
    try:
        for index, digit in enumerate(text):
            if index:
                time.sleep(0.002)
            for down in (True, False):
                event = create(source, keycodes[digit], down)
                if not event:
                    raise RuntimeError('Could not create keyboard event')
                try:
                    flags(event, 1 << 21)  # Numeric keypad, no Hyper modifiers.
                    # Enter after device/session remapping. Posting at HID lets
                    # Hyperkey turn these digits into shortcuts while Caps is held.
                    post(2, event)
                finally:
                    release(event)
    finally:
        release(source)


def daemon():
    """Keep OCR warm and register the effective Hyper+backslash hotkey."""
    import fcntl
    import queue
    import threading
    from pathlib import Path
    import warnings
    warnings.filterwarnings('ignore', category=UserWarning, module='objc._bridgesupport')
    import AppKit
    import ApplicationServices as AX
    import Quartz

    # Register hotkeys without becoming a foreground app or a Dock item.
    background_app = AppKit.NSApplication.sharedApplication()
    if not background_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited):
        raise RuntimeError('Could not set background-only activation policy')

    accessibility = AX.AXIsProcessTrusted()
    screen_recording = Quartz.CGPreflightScreenCaptureAccess()
    print(json.dumps({'accessibility':bool(accessibility), 'screen_recording':bool(screen_recording)}), flush=True)
    if not accessibility or not screen_recording:
        print('Grant python3.9 its own macOS Accessibility and Screen Recording access, then restart the helper.', file=sys.stderr, flush=True)
        raise SystemExit(0)

    def foreground():
        application = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return application.processIdentifier(), application.bundleIdentifier()

    cache = Path(__file__).resolve().parent / '.runtime'
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (cache / 'daemon.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Autofill helper is already running')
    lock.write(str(os.getpid()))
    lock.flush()
    requests = queue.Queue(maxsize=1)
    ready = threading.Event()
    busy = threading.Event()

    def worker():
        api = OCR()
        try:
            with Capture() as screen:
                # Establish the capture connection before the first hotkey.
                screen.grab(REGION)
                ready.set()
                while True:
                    target = requests.get()
                    try:
                        shot = screen.grab(REGION)
                        code = api.digits(shot.rgb, shot.width, shot.height)
                        if foreground()[0] == target:
                            type_digits(code)
                            print(json.dumps({'event':'entered', 'digit_count':len(code)}), flush=True)
                        else:
                            print(json.dumps({'event':'cancelled', 'reason':'foreground_changed'}), flush=True)
                    except Exception as error:
                        print(f'Autofill failed: {error}', file=sys.stderr, flush=True)
                    finally:
                        busy.clear()
                        requests.task_done()
        finally:
            api.close()

    threading.Thread(target=worker, daemon=True).start()
    if not ready.wait(10):
        raise RuntimeError('Capture/OCR worker failed to initialize')
    # Secure password fields stop delivering keystrokes to event taps. Register
    # this single shortcut with macOS instead of monitoring the keyboard stream.
    carbon = C.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')

    class EventType(C.Structure):
        _fields_ = [('event_class', C.c_uint32), ('kind', C.c_uint32)]

    class HotKeyID(C.Structure):
        _fields_ = [('signature', C.c_uint32), ('id', C.c_uint32)]

    callback_type = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p)
    get_kind = bind(carbon, 'GetEventKind', C.c_uint32, C.c_void_p)
    pressed = False

    @callback_type
    def observe(handler, event, context):
        nonlocal pressed
        if get_kind(event) == 6:  # kEventHotKeyReleased
            pressed = False
            return 0
        if not pressed:
            pressed = True
            target, bundle = foreground()
            if not busy.is_set():
                busy.set()
                requests.put_nowait(target)
                print(json.dumps({'event':'hotkey', 'target':bundle}), flush=True)
        return 0

    target = bind(carbon, 'GetApplicationEventTarget', C.c_void_p)()
    event_class = int.from_bytes(b'keyb', 'big')
    types = (EventType * 2)(EventType(event_class, 5), EventType(event_class, 6))
    handler = C.c_void_p()
    install = bind(carbon, 'InstallEventHandler', C.c_int32, C.c_void_p,
                   callback_type, C.c_uint32, C.POINTER(EventType), C.c_void_p,
                   C.POINTER(C.c_void_p))
    status = install(target, observe, 2, types, None, C.byref(handler))
    if status:
        raise RuntimeError(f'Could not install hotkey handler: {status}')
    register = bind(carbon, 'RegisterEventHotKey', C.c_int32, C.c_uint32,
                    C.c_uint32, HotKeyID, C.c_void_p, C.c_uint32,
                    C.POINTER(C.c_void_p))
    hotkey = C.c_void_p()
    # Carbon modifier bits: Command, Shift, Option, Control.
    modifiers = (1 << 8) | (1 << 9) | (1 << 11) | (1 << 12)
    status = register(42, modifiers, HotKeyID(int.from_bytes(b'2FAK', 'big'), 1),
                      target, 0, C.byref(hotkey))
    if status:
        raise RuntimeError(f'Could not register Hyper+backslash: {status}')
    print('Autofill helper ready (registered Hyper+backslash)', flush=True)
    bind(carbon, 'RunApplicationEventLoop', None)()


if __name__ == '__main__':
    if '--daemon' not in sys.argv:
        raise SystemExit('Use manage_helper.py install or restart to run the background helper.')
    daemon()
