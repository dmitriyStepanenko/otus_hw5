import logging
import mimetypes
from time import strftime
from urllib.parse import unquote
from constants import DEFAULT_HTTP_PROTOCOL
from http import HTTPStatus
from pathlib import Path


class Response:
    def __init__(
            self,
            protocol=DEFAULT_HTTP_PROTOCOL,
            server_name=None,
            allowed_methods=None,
            allowed_http_protocols=None,
            root_dir=None
    ):
        self.status: HTTPStatus = None
        self.headers = {
            'Server': server_name,
            'Date': strftime('%c'),
            'Connection': 'keep-alive',
            'Content-Type': None,
            'Content-Length': 0,
        }
        self.body = b''
        self.protocol = protocol

        self.allowed_methods = allowed_methods
        self.allowed_http_protocols = allowed_http_protocols
        self.root_dir = root_dir

    def form_response_no_return(self, sock_data):
        data = sock_data.inb
        try:
            # в запросе нет тела, т.к. это get и head запросы
            # вроде как рекомендуется серверам уметь работать
            # с запросами в которых перенос реализован через один \n
            method_url_protocol = data.decode('iso-8859-1').replace('\r\n', '\n').split('\n')[0]

            method = method_url_protocol.split(' ')[0]
            if method not in self.allowed_methods:
                self.status = HTTPStatus.METHOD_NOT_ALLOWED
                sock_data.resp = self.render()
                return

            protocol = method_url_protocol[-len(self.protocol):]
            if protocol not in self.allowed_http_protocols:
                raise ValueError(f'Сервер работает только с протоколами {self.allowed_http_protocols}')

            # +1 и -1  нужны т.к. там пробелы по краям
            url = self.prepare_url(method_url_protocol[len(method) + 1: - len(protocol) - 1])

            if method == 'HEAD':
                self.headers['Content-Length'] = Path(url).stat().st_size
            else:
                self.body = load(url)
                logging.info(f'тело ответа {self.body} успешно прочитано из файла')

                self.headers['Content-Length'] = len(self.body.decode("iso-8859-1"))

            if not self.headers['Content-Length']:
                self.status = HTTPStatus.NOT_FOUND
                sock_data.resp = self.render()
                return

            self.status = HTTPStatus.OK

        except (FileNotFoundError, NotADirectoryError):
            logging.error('файл не найден')
            self.status = HTTPStatus.NOT_FOUND

        except Exception as e:
            logging.error(f'Ошибка парсинга: {e} - {data}')
            self.status = HTTPStatus.FORBIDDEN

        sock_data.resp = self.render()

    def prepare_url(self, url):
        url = unquote(url.split('?')[0])

        url = url + 'index.html' if url[-1] == '/' else url
        url = Path(self.root_dir + url).resolve()

        if not url.is_relative_to(self.root_dir):
            raise FileNotFoundError()

        url = str(url)
        content_type = mimetypes.guess_type(url)
        self.headers['Content-Type'] = content_type[0]

        return url

    def render(self):
        status_line = f'{self.protocol} {self.status.value} {self.status.name}\r\n'

        header_line = ''
        if self.headers:
            for key, value in self.headers.items():
                header_line += f'{key}: {value}\r\n'

        return (status_line + header_line + '\r\n').encode('iso-8859-1') + self.body


def load(path: str) -> bytes:
    logging.info(f'пытаемся прочитать {path}')
    with open(path, 'rb') as f:
        return f.read()
