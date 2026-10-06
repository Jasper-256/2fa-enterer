import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="objc._bridgesupport")
import time
import re
from pynput.keyboard import Controller as _KeyboardController
import tesserocr
import mss
from PIL import Image

_keyboard = _KeyboardController()
_api = tesserocr.PyTessBaseAPI(path="/opt/homebrew/opt/tesseract/share/tessdata", psm=tesserocr.PSM.SINGLE_BLOCK)
_api.SetVariable("tessedit_char_whitelist", "0123456789")
_sct = mss.mss()

def capture_center_screen():
    monitor = {"left": 674, "top": 442, "width": 162, "height": 40}
    raw = _sct.grab(monitor)
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

def extract_numbers(image):
    _api.SetImage(image)
    text = _api.GetUTF8Text()
    return re.sub(r'\D', '', text)

def main():
    screenshot = capture_center_screen()
    code = extract_numbers(screenshot)
    for ch in code:
        _keyboard.press(ch)
        _keyboard.release(ch)
        time.sleep(0.01)

if __name__ == "__main__":
    main()
