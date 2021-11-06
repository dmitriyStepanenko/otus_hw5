from queue import Queue
from threading import Thread
import logging


class Worker(Thread):
    """
    Поток исполняющий задачи из очереди задач
    """
    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()
        logging.info(f'Воркер {self.name} запущен')

    def run(self):
        while True:
            func, args, kargs = self.tasks.get()
            try:
                func(*args, **kargs)
                logging.info(f'Задача выполнена воркером {self.name}')
            except Exception as e:
                logging.error(f'Выполнение задачи воркером {self.name} завершилась с ошибкой: {e}')
            finally:
                self.tasks.task_done()


class ThreadPool:
    """
    Пул потоков в которые отправляются задачи из очереди
    """
    def __init__(self, num_threads):
        self.tasks = Queue(num_threads)
        for _ in range(num_threads):
            Worker(self.tasks)
        logging.info(f'Создано {num_threads} воркеров')

    def add_task(self, func, *args, **kargs):
        """
        Добавляем задачу в очередь
        """
        self.tasks.put((func, args, kargs), block=True)

    def map(self, func, args_list):
        """
        Добавляем список одинаковых задач с разными аргументами в очередь
        """
        for args in args_list:
            self.add_task(func, args)

    def wait_completion(self):
        """
        Ждем завершения всех задач в очереди
        """
        self.tasks.join()
