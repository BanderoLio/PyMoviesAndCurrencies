"""
Многопоточный TCP-сервер с парсингом HTTP-запросов.

Сервер обрабатывает HTTP-запросы, парсит их и предоставляет различные сервисы:
- Курсы валют (/exchange?currency=USD) - использует exchangerate-api.io
- Информация о фильме (/movie?title=Название) - использует OMDB API
"""

import json
import socket
import threading
from http.client import HTTPResponse
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import urlopen

HOST: str = "localhost"
PORT: int = 8888
BUFFER_SIZE: int = 4096
ENCODING: str = "utf-8"
TIMEOUT: int = 10  # Таймаут для HTTP-запросов к API (секунды)

OMDB_API_KEY: str = "YOUR_API_KEY"


def parse_http_request(request: str) -> tuple[str, str, dict[str, list[str]]]:
    """
    Парсит HTTP-запрос и извлекает метод, путь и параметры запроса.

    Args:
        request: Строка с HTTP-запросом

    Returns:
        Кортеж из (метод, путь, словарь параметров)
    """
    lines: list[str] = request.split("\r\n")
    if not lines:
        return "", "", {}

    # Парсинг первой строки запроса (Request Line)
    request_line: str = lines[0]
    parts: list[str] = request_line.split()

    if len(parts) < 2:
        return "", "", {}

    method: str = parts[0]  # GET, POST, etc.
    full_path: str = parts[1]  # /path?param=value

    # Парсинг URL для извлечения пути и параметров
    parsed_url = urlparse(full_path)
    path: str = parsed_url.path

    # Парсинг query параметров
    query_params: dict[str, list[str]] = parse_qs(parsed_url.query)

    return method, path, query_params


def handle_exchange_request(params: dict[str, list[str]]) -> str:
    """
    Обрабатывает запрос курсов валют, используя
     реальное API exchangerate-api.io.

    Args:
        params: Словарь параметров запроса

    Returns:
        HTML-ответ с курсом валюты
    """
    currency: str = params.get("currency", ["USD"])[0].upper()

    # Названия валют для отображения
    currency_names: dict[str, str] = {
        "USD": "Доллар США",
        "EUR": "Евро",
        "GBP": "Фунт стерлингов",
        "JPY": "Японская иена",
        "CNY": "Китайский юань",
        "RUB": "Российский рубль",
        "CAD": "Канадский доллар",
        "AUD": "Австралийский доллар",
    }

    try:
        # Получение курсов валют через API
        # API возвращает курсы относительно базовой валюты (USD)
        api_url: str = "https://api.exchangerate-api.com/v4/latest/USD"

        with urlopen(api_url, timeout=TIMEOUT) as response:
            assert isinstance(response, HTTPResponse)
            data: dict[str, Any] = json.loads(response.read().decode(ENCODING))

        rates: dict[str, float] = data.get("rates", {})
        date: str = data.get("date", "Неизвестно")

        if currency not in rates:
            html_response: str = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="utf-8">
                    <title>Валюта не найдена</title>
                </head>
                <body>
                    <h1>Ошибка</h1>
                    <p>Валюта {currency} не найдена в базе данных.</p>
                    <p>Доступные валюты: USD, EUR, GBP, JPY, CNY, RUB, CAD, AUD и другие</p>
                    <a href="/">На главную</a>
                </body>
            </html>
            """
            return html_response

        # Получение курса валюты относительно USD
        rate_to_usd: float = rates.get(currency, 1.0)

        # Получение курса RUB относительно USD
        rate_rub: float = rates.get("RUB", 1.0)

        # Конвертация: 1 единица валюты = X RUB
        rate_to_rub: float = rate_rub / rate_to_usd if rate_to_usd != 0 else 0

        currency_name: str = currency_names.get(currency, currency)

        html_response = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Курс {currency}</title>
                <style>
                    body {{
                        font-family: Monocraft, sans-serif;
                        max-width: 600px;
                        margin: 50px auto;
                        padding: 20px;
                    }}
                    h1 {{ color: #333; }}
                    .rate {{ font-size: 24px; color: #0066cc; margin: 20px 0; }}
                    .info {{ color: #666; }}
                </style>
            </head>
            <body>
                <h1>Курс валюты</h1>
                <p><strong>{currency_name} ({currency})</strong></p>
                <div class="rate">1 {currency} = {rate_to_rub:.2f} RUB</div>
                <div class="rate">1 USD = {rate_to_usd:.4f} {currency}</div>
                <p class="info">Дата обновления: {date}</p>
                <p class="info">Источник: exchangerate-api.io</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """

    except (HTTPError, URLError) as e:
        print(f"[Ошибка API] Ошибка при получении курсов валют: {e}")
        html_response = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка API</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Не удалось получить данные о курсе валюты {currency}.</p>
                <p>Проверьте подключение к интернету и попробуйте позже.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Ошибка парсинга] Ошибка при обработке ответа API: {e}")
        html_response = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка обработки</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Ошибка при обработке данных от API.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """
    except Exception as e:
        print(
            f"[Ошибка] Неожиданная ошибка при обработке "
            f"запроса курса валют: {e}"
        )
        html_response = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Произошла ошибка при обработке запроса.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """

    return html_response


def handle_movie_request(params: dict[str, list[str]]) -> str:
    """
    Обрабатывает запрос информации о фильме, используя реальное API OMDB.

    Args:
        params: Словарь параметров запроса

    Returns:
        HTML-ответ с информацией о фильме
    """
    title: str = params.get("title", ["Неизвестно"])[0]

    if not title or title == "Неизвестно":
        html_response: str = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Не указано название фильма.</p>
                <p>Используйте: /movie?title=Название фильма</p>
                <a href="/">На главную</a>
                <a href="/movies">Искать другие фильмы</a>
            </body>
        </html>
        """
        return html_response

    try:
        # Получение информации о фильме через OMDB API
        encoded_title: str = quote(title)
        api_url: str = (
            f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}"
        )

        with urlopen(api_url, timeout=TIMEOUT) as response:
            assert isinstance(response, HTTPResponse)
            data: dict[str, Any] = json.loads(response.read().decode(ENCODING))

        # Проверка ответа API
        if data.get("Response") == "False":
            error_msg: str = data.get("Error", "Фильм не найден")
            html_response = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="utf-8">
                    <title>Фильм не найден</title>
                </head>
                <body>
                    <h1>Ошибка</h1>
                    <p>{error_msg}</p>
                    <a href="/">На главную</a>
                    <a href="/movies">Искать другие фильмы</a>
                </body>
            </html>
            """
            return html_response

        # Извлечение данных о фильме
        movie_title: str = data.get("Title", "Неизвестно")
        year: str = data.get("Year", "Неизвестно")
        director: str = data.get("Director", "Неизвестно")
        rating: str = data.get("imdbRating", "Неизвестно")
        plot: str = data.get("Plot", "Описание отсутствует")
        genre: str = data.get("Genre", "Неизвестно")
        actors: str = data.get("Actors", "Неизвестно")
        poster: str = data.get("Poster", "")

        # Формирование HTML-ответа
        poster_html: str = ""
        if poster and poster != "N/A":
            poster_html = f'<img src="{poster}" alt="Постер {movie_title}" style="max-width: 300px; margin: 20px 0;">'

        html_response = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>{movie_title}</title>
                <style>
                    body {{
                        font-family: Monocraft, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                    }}
                    h1 {{ color: #333; }}
                    .info {{ margin: 10px 0; }}
                    .label {{ font-weight: bold; color: #666; }}
                    .rating {{ color: #0066cc; font-size: 18px; }}
                </style>
            </head>
            <body>
                <h1>{movie_title}</h1>
                {poster_html}
                <div class="info"><span class="label">Год:</span> {year}</div>
                <div class="info"><span class="label">Режиссер:</span> {director}</div>
                <div class="info"><span class="label">Жанр:</span> {genre}</div>
                <div class="info"><span class="label">Актеры:</span> {actors}</div>
                <div class="info"><span class="label">Рейтинг IMDb:</span> <span class="rating">{rating}/10</span></div>
                <div class="info"><span class="label">Описание:</span> {plot}</div>
                <p style="margin-top: 30px;"><a href="/">На главную</a></p>
                <p><a href="/movies">Искать другие фильмы</a></p>
            </body>
        </html>
        """

    except (HTTPError, URLError) as e:
        print(f"[Ошибка API] Ошибка при получении информации о фильме: {e}")
        html_response = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка API</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Не удалось получить информацию о фильме "{title}".</p>
                <p>Проверьте подключение к интернету и попробуйте позже.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Ошибка парсинга] Ошибка при обработке ответа API: {e}")
        html_response = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка обработки</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Ошибка при обработке данных от API.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """
    except Exception as e:
        print(f"[Ошибка] Неожиданная ошибка при обработке запроса фильма: {e}")
        html_response = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <title>Ошибка</title>
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Произошла ошибка при обработке запроса.</p>
                <a href="/">На главную</a>
            </body>
        </html>
        """

    return html_response


def create_http_response(
    status_code: int, status_text: str, body: str
) -> bytes:
    """
    Создает HTTP-ответ в байтовом формате.

    Args:
        status_code: HTTP код статуса
        status_text: Текст статуса
        body: Тело ответа (HTML)

    Returns:
        HTTP-ответ в байтах
    """
    headers: str = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body.encode(ENCODING))}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    response: bytes = headers.encode(ENCODING) + body.encode(ENCODING)
    return response


def get_index_page() -> str:
    """
    Возвращает главную страницу с навигацией.

    Returns:
        HTML главной страницы
    """
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset="utf-8">
            <title>TCP HTTP Server</title>
            <style>
                body { 
                    font-family: Monocraft, sans-serif; max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                }
                h1 { color: #333; }
                ul { list-style-type: none; padding: 0; }
                li { margin: 10px 0; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>Многопоточный TCP HTTP Server</h1>
            <p>Доступные сервисы:</p>
            <ul>
                <li><a href="movies">Поиск фильмов</a></li>
                <li><a href="/exchange?currency=USD">Курсы валют (USD)</a></li>
                <li><a href="/exchange?currency=EUR">Курсы валют (EUR)</a></li>
                <li><a href="/exchange?currency=GBP">Курсы валют (GBP)</a></li>
                <li><a href="/exchange?currency=JPY">Курсы валют (JPY)</a></li>
                <li><a href="/movie?title=Matrix">Информация о фильме: Matrix</a></li>
                <li><a href="/movie?title=Inception">Информация о фильме: Inception</a></li>
                <li><a href="/movie?title=The Shawshank Redemption">Информация о фильме: The Shawshank Redemption</a></li>
            </ul>
        </body>
    </html>
    """


def get_search_movies():
    """
    Возвращает страницу с поиском фильмов.

    Returns:
        HTML страницы c поиском фильмов
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8" />
        <title>Поиск фильмов</title>
        <style>
            body {
                    font-family: Monocraft, sans-serif; max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                }
                h1 { color: #333; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <form action="/movie" method="get">
        <h1>Поиск фильмов</h1>
        <input type="text" name="title" placeholder="Название фильма">
        <button type="submit">Найти</button>
        </form>
        <p style="margin-top: 30px;"><a href="/">На главную</a></p>
    </body>
    </html>
    """


def handle_client(
    client_socket: socket.socket, address: tuple[str, int]
) -> None:
    """
    Обрабатывает подключение клиента в отдельном потоке.

    Args:
        client_socket: Сокет клиента
        address: Адрес клиента (хост, порт)
    """
    try:
        print(f"[Подключение] Клиент {address[0]}:{address[1]} подключен")

        # Получение HTTP-запроса
        request_data: bytes = client_socket.recv(BUFFER_SIZE)
        if not request_data:
            return

        # Декодирование запроса
        request_str: str = request_data.decode(ENCODING)
        print(f"[Запрос от {address[0]}:{address[1]}]")
        print("-" * 50)
        print(request_str)
        print("-" * 50)

        # Парсинг HTTP-запроса
        method, path, params = parse_http_request(request_str)

        # Определение сервиса и формирование ответа
        response_body: str = ""
        status_code: int = 200
        status_text: str = "OK"

        if path == "/" or path == "":
            response_body = get_index_page()
        elif path == "/movies":
            response_body = get_search_movies()
        elif path == "/exchange":
            response_body = handle_exchange_request(params)
        elif path == "/movie":
            response_body = handle_movie_request(params)
        else:
            response_body = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="utf-8">
                    <title>404 - Не найдено</title>
                </head>
                <body>
                    <h1>404 - Страница не найдена</h1>
                    <p>Путь {path} не найден на сервере.</p>
                    <a href="/">На главную</a>
                </body>
            </html>
            """
            status_code = 404
            status_text = "Not Found"

        # Формирование и отправка HTTP-ответа
        response: bytes = create_http_response(
            status_code, status_text, response_body
        )
        client_socket.sendall(response)

        print(f"[Ответ] Отправлен ответ клиенту {address[0]}:{address[1]}")

    except UnicodeDecodeError:
        print(
            f"[Ошибка] Не удалось декодировать запрос от {address[0]}:{address[1]}"
        )
        error_response: bytes = create_http_response(
            400,
            "Bad Request",
            "<h1>400 - Bad Request</h1><p>Неверный формат запроса</p>",
        )
        client_socket.sendall(error_response)
    except Exception as e:
        print(
            f"[Ошибка] Ошибка при обработке клиента {address[0]}:{address[1]}: {e}"
        )
        error_response: bytes = create_http_response(
            500,
            "Internal Server Error",
            "<h1>500 - Internal Server Error</h1>",
        )
        try:
            client_socket.sendall(error_response)
        except Exception:
            pass
    finally:
        # Закрытие сокета клиента
        try:
            client_socket.close()
            print(f"[Отключение] Клиент {address[0]}:{address[1]} отключен")
        except Exception:
            pass


def main() -> None:
    """
    Основная функция сервера.
    Создает сокет, привязывает его к порту и запускает обработку клиентов.
    """
    # Создание TCP сокета
    server_socket: socket.socket = socket.socket(
        socket.AF_INET, socket.SOCK_STREAM
    )
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # Привязка сокета к адресу и порту
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"[Сервер] Запущен на {HOST}:{PORT}")
        print("[Сервер] Ожидание подключений...")
        print(f"[Сервер] Откройте в браузере: http://{HOST}:{PORT}")

        # Основной цикл обработки подключений
        while True:
            # Принятие подключения
            client_socket, address = server_socket.accept()

            # Создание потока для обработки клиента
            client_thread: threading.Thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True,
            )
            client_thread.start()
            print(
                f"[Поток] Запущен поток для клиента {address[0]}:{address[1]}"
            )

    except KeyboardInterrupt:
        print("\n[Сервер] Получен сигнал завершения (Ctrl+C)")
    except Exception as e:
        print(f"[Ошибка] Критическая ошибка сервера: {e}")
    finally:
        # Закрытие серверного сокета
        try:
            server_socket.close()
            print("[Сервер] Сервер остановлен")
        except Exception:
            pass


if __name__ == "__main__":
    main()
