import logging
from pathlib import Path
import socket
import selectors
import types
from optparse import OptionParser
from response import Response
from concurrent.futures import ThreadPoolExecutor
from constants import DEFAULT_HTTP_PROTOCOL
from constants import OLD_HTTP_PROTOCOL


SERVER_NAME = 'Python server'


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
        self.sel = selectors.PollSelector()
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
        self.thread_pool = ThreadPoolExecutor(workers)

    def run_server(self, host=None, port=None):
        host = self.host if host is None else host
        port = self.port if port is None else port
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 10)
        lsock.bind((host, port))
        lsock.listen(100)
        logging.info(f"listening on {host} {port}")
        lsock.setblocking(False)
        self.sel.register(lsock, selectors.EVENT_READ, data=None)

    def serve_forever(self):
        try:
            while True:
                events = self.sel.select(timeout=1)
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
        events = selectors.EVENT_READ
        self.sel.register(conn, events, data=data)

    def service_connection(self, socket_with_data, mask):
        sock: socket.socket = socket_with_data.fileobj
        data = socket_with_data.data
        if mask & selectors.EVENT_READ:
            recv_data = self.recv(sock, 1024)
            logging.info(f"get {recv_data}")
            if not recv_data:
                logging.info(f"closing connection to {data.addr}")
                self.sel.unregister(sock)
                sock.close()
                return

            data.inb += recv_data
            if data.inb.decode('utf-8').replace('\r\n', '\n').find('\n\n') != -1:
                logging.info('find end of headers')
                resp = Response(
                    protocol=self.protocol,
                    server_name=self.server_name,
                    allowed_methods=self.allowed_methods,
                    allowed_http_protocols=self.allowed_http_protocols,
                    root_dir=self.root_dir
                )
                self.sel.modify(sock, selectors.EVENT_WRITE, data)
                self.thread_pool.submit(resp.form_response_no_return, data)

        if mask & selectors.EVENT_WRITE:
            if not data.resp:
                return

            logging.info(f"try send {data.resp} to {data.addr}")
            n = self.send(sock, data.resp)
            logging.info(f"send {n} from {len(data.resp)} bytes ")

            if n < len(data.resp):
                data.resp = data.resp[n:]
            else:
                self.sel.unregister(sock)
                sock.close()

    def recv(self, sock, size):
        try:
            return sock.recv(size)
        except ConnectionResetError:
            logging.info('Connection reset by peer')
            self.sel.unregister(sock)
            sock.close()

    def send(self, sock, data):
        try:
            return sock.send(data)
        except ConnectionResetError:
            logging.info('Connection reset by peer')
            self.sel.unregister(sock)
            sock.close()

    def close(self):
        self.thread_pool.shutdown()
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
