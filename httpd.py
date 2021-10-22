import json
import logging
from pathlib import Path
import sys
import socket
import selectors
import types
from optparse import OptionParser
import mimetypes
from time import strftime
from collections import namedtuple
from urllib.parse import unquote
from threadpool import ThreadPool


SERVER_NAME = 'Python server'
HTTP_STATUS_OK = '200 OK'
HTTP_STATUS_FORBIDDEN = '403 Forbidden'
HTTP_STATUS_NOT_FOUND = '404 Not Found'
HTTP_STATUS_METHOD_NOT_ALLOWED = '405 Method Not Allowed'
HTTP_STATUS_INTERNAL_SERVER_ERROR = '500 Internal server error'
HTTP_STATUS_BAD_REQUEST = '400 Bad Request'

DEFAULT_HTTP_PROTOCOL = 'HTTP/1.0'
OLD_HTTP_PROTOCOL = 'HTTP/1.1'


Response = namedtuple(
    typename='Response',
    field_names=['status', 'headers', 'body', 'protocol'],
    defaults=[None, None, b'', DEFAULT_HTTP_PROTOCOL])


class Server:
    def __init__(
            self,
            host='localhost',
            port=8080,
            root_dir='',
            workers=1,
            server_name=SERVER_NAME,
            protocol=DEFAULT_HTTP_PROTOCOL,
            autorun=True
    ):
        self.sel = selectors.DefaultSelector()
        self.host = host
        self.port = port

        if autorun:
            self.run_server()

        self.root_dir = root_dir
        self.server_name = server_name
        self.protocol = protocol
        self.allowed_http_protocols = [DEFAULT_HTTP_PROTOCOL, OLD_HTTP_PROTOCOL]
        self.allowed_methods = ['GET', 'HEAD']
        self.count_workers = workers
        self.thread_pool = ThreadPool(workers)

    def run_server(self, host=None, port=None):
        host = self.host if host is None else host
        port = self.port if port is None else port
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind((host, port))
        lsock.listen(1)
        logging.info(f"listening on {host} {port}")
        lsock.setblocking(False)
        self.sel.register(lsock, selectors.EVENT_READ, data=None)

    def serve_forever(self):
        try:
            while True:
                events = self.sel.select(timeout=None)
                for socket_with_data, mask in events:
                    if socket_with_data.data is None:
                        self.accept_wrapper(socket_with_data.fileobj)
                    else:
                        self.service_connection(socket_with_data, mask)
        except KeyboardInterrupt:
            logging.info("caught keyboard interrupt, exiting")
        finally:
            self.close()

    def accept_wrapper(self, sock):
        conn, addr = sock.accept()
        logging.info(f"accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"", resp=None)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    def service_connection(self, socket_with_data, mask):
        sock: socket.socket = socket_with_data.fileobj
        data = socket_with_data.data
        if mask & selectors.EVENT_READ:
            while True:
                recv_data = self.recv(sock, 1024)
                logging.info(f"get {recv_data}")
                if not recv_data:
                    logging.info(f"closing connection to {data.addr}")
                    self.sel.unregister(sock)
                    sock.close()
                    return

                data.inb += recv_data
                if recv_data.decode('utf-8').replace('\r\n', '\n').find('\n\n') != -1:
                    logging.info('find end of headers')
                    break
            self.thread_pool.add_task(self.form_response_no_return, socket_with_data.data)

        if mask & selectors.EVENT_WRITE:
            if data.resp:
                sending_data = self.send_response(sock, data.resp)
                logging.info(f"send {sending_data} to {data.addr}")

                self.sel.unregister(sock)
                sock.close()

    def form_response_no_return(self, sock_data):
        data = sock_data.inb
        headers = {
            'Server': self.server_name,
            'Date': strftime('%c'),
            'Connection': 'keep-alive',
            'Content-Type': None,
            'Content-Length': 0,
        }
        try:
            # в запросе нет тела, т.к. это get и head запросы
            # вроде как рекомендуется серверам уметь работать
            # с запросами в которых перенос реализован через один \n
            method_url_protocol = data.decode('iso-8859-1').replace('\r\n', '\n').split('\n')[0]

            method = method_url_protocol.split(' ')[0]
            if method not in self.allowed_methods:
                sock_data.resp = Response(HTTP_STATUS_METHOD_NOT_ALLOWED, headers, protocol=self.protocol)
                return

            protocol = method_url_protocol[-len(self.protocol):]
            if protocol not in self.allowed_http_protocols:
                raise ValueError(f'Сервер работает только с протоколами {self.allowed_http_protocols}')

            url = method_url_protocol[len(method) + 1: - len(protocol) - 1]  # +1 и -1  нужны т.к. там пробелы по краям

            url = unquote(url.split('?')[0])

            if '/../' in url:
                sock_data.resp = Response(HTTP_STATUS_BAD_REQUEST, headers, protocol=protocol)
                return

            url = url + 'index.html' if url[-1] == '/' else url
            body = self.load(url)
            logging.info(f'тело ответа {body.decode("iso-8859-1")} успешно прочитано из файла')

            if not len(body):
                sock_data.resp = Response(HTTP_STATUS_NOT_FOUND, headers, protocol=protocol)
                return

            content_type = mimetypes.guess_type(url)
            headers['Content-Type'] = content_type[0]
            headers['Content-Length'] = len(body.decode("iso-8859-1"))
            if method == 'HEAD':
                body = b''

            sock_data.resp = Response(HTTP_STATUS_OK, headers, body, protocol)

        except (FileNotFoundError, NotADirectoryError):
            logging.error('файл не найден')
            sock_data.resp = Response(HTTP_STATUS_NOT_FOUND, headers, protocol=self.protocol)

        except Exception as e:
            logging.error(f'Ошибка парсинга: {e} - {data}')
            sock_data.resp = Response(HTTP_STATUS_FORBIDDEN, headers, protocol=self.protocol)

    def load(self, url: str) -> bytes:
        logging.info(f'пытаемся прочитать {self.root_dir + url}')
        with open(self.root_dir + url, 'rb') as f:
            return f.read()

    def recv(self, sock, size):
        try:
            return sock.recv(size)
        except ConnectionResetError:
            logging.info('Connection reset by peer')
            self.sel.unregister(sock)
            sock.close()

    def sendall(self, sock, data):
        try:
            return sock.sendall(data)
        except ConnectionResetError:
            logging.info('Connection reset by peer')
            self.sel.unregister(sock)
            sock.close()

    def send_response(self, sock, resp: Response):
        status_line = f'{resp.protocol} {resp.status}\r\n'

        header_line = ''
        if resp.headers:
            for key, value in resp.headers.items():
                header_line += f'{key}: {value}\r\n'

        out_data = (status_line + header_line + '\r\n').encode('iso-8859-1') + resp.body
        self.sendall(sock, out_data)
        return out_data

    def close(self):
        self.sel.close()


def main():
    op = OptionParser()
    op.add_option("-p", "--port", type=int, default=8080)
    op.add_option("-l", "--log", default=None)
    op.add_option("-w", "--workers", type=int, default=4)
    op.add_option("-r", "--root_dir", type=str, default=str(Path(__file__).parent))
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log, level=logging.INFO,
                        format='[%(asctime)s] %(levelname).1s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')
    server = Server(
        host='localhost',
        port=opts.port,
        root_dir=opts.root_dir,
        workers=opts.workers)
    logging.info("Starting server at %s" % opts.port)
    server.serve_forever()


if __name__ == '__main__':
    main()
