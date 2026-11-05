"""Простая проверка сервиса без сторонних библиотек: python check_health.py."""
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main():
    try:
        with urlopen("http://localhost:8000/smeshariki-quotes", timeout=5) as response:
            print("Сервис доступен:", response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        print("Сервис недоступен:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
